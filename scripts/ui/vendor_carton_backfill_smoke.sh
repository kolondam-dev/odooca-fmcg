#!/usr/bin/env bash
# Runs only against the disposable PostgreSQL service of the Odoo install CI job.
set -euo pipefail

fixture=$(mktemp -d)
trap 'rm -rf "$fixture"' EXIT
chmod 755 "$fixture"
mkdir -p "$fixture/data/seed"
cat > "$fixture/data/seed/products_150.csv" <<'CSV'
default_code,principal_code,purchase_uom,carton_qty,cost_price
CI-CARTON-1,CI-CARTON,Karton,120,1250
CI-CARTON-2,CI-CARTON,Karton,120,1250
CSV
printf 'code,lead_time_days\nCI-CARTON,12\n' > "$fixture/data/seed/principals_4.csv"

shell() {
    docker run --rm -i --network host -v "$fixture:/fixture:ro" -w /fixture \
        -e FMCG_VENDOR_CARTON_MODE -e FMCG_VENDOR_CARTON_COMPANY_ID \
        --entrypoint bash fmcg-odoo:ci -c '
        odoo shell -d vendor_carton_ci --db_host localhost --db_port 5432 -r odoo -w odoo \
            --addons-path "$( /opt/deploy/addons_path.sh )" --no-http
    '
}

docker run --rm --network host -e PGPASSWORD=odoo --entrypoint createdb fmcg-odoo:ci \
    -h localhost -U odoo -T ci_db vendor_carton_ci
company=$(shell <<'PY' | sed -n 's/^TARGET_COMPANY=//p'
currency = env.ref("base.EUR") if env.company.currency_id != env.ref("base.EUR") else env.ref("base.USD")
currency.active = True
target = env["res.company"].create({"name": "Carton Backfill Target", "currency_id": currency.id})
assert env.company != target
vendor = env["res.partner"].create({"name": "Carton Backfill Vendor"})
principal = env["id.principal"].create({"name": "Backfill", "code": "CI-CARTON", "partner_id": vendor.id})
for number in (1, 2):
    product = env["product.template"].create({
        "name": f"Backfill product {number}",
        "default_code": f"CI-CARTON-{number}",
        "company_id": target.id,
        "principal_id": principal.id,
        "uom_id": env.ref("uom.product_uom_unit").id,
    })
    product.configure_fmcg_packaging_uoms(env.ref("id_base.uom_pcs"), 10, 120)

env.flush_all()
env.cr.execute("""
    CREATE TABLE ci_backfill_snapshot (name text PRIMARY KEY, digest text);
    CREATE FUNCTION ci_backfill_digest(table_name text) RETURNS text LANGUAGE plpgsql AS $$
    DECLARE digest text;
    BEGIN
      EXECUTE format('SELECT md5(COALESCE(string_agg(row_to_json(t)::text, '''' ORDER BY id), '''')) FROM %I t',
                     table_name) INTO digest;
      RETURN digest;
    END $$;
    INSERT INTO ci_backfill_snapshot
    SELECT name, ci_backfill_digest(name)
    FROM unnest(ARRAY['product_template','uom_uom','stock_quant','purchase_order','purchase_order_line',
                      'account_move','account_move_line']) AS rows(name);
""")
env.cr.commit()
print(f"TARGET_COMPANY={target.id}")
PY
)
export FMCG_VENDOR_CARTON_COMPANY_ID="$company"
[[ "$company" =~ ^[0-9]+$ ]]

operator() {
    FMCG_VENDOR_CARTON_MODE="$1" shell < scripts/load_fmcg_seed.py
}

verify() {
    shell <<PY
target = env["res.company"].browse($company)
assert env.company != target
offers = env["product.supplierinfo"].sudo().search([("product_tmpl_id.default_code", "in",
                                                    ["CI-CARTON-1", "CI-CARTON-2"])])
assert len(offers) == $1, offers
for offer in offers:
    assert offer.company_id == target
    assert offer.currency_id == target.currency_id
    assert offer.product_uom_id == offer.product_tmpl_id.fmcg_carton_uom_id
    assert offer.price == 150000 and offer.delay == 12
env.cr.execute("SELECT name FROM ci_backfill_snapshot WHERE digest <> ci_backfill_digest(name)")
changed = env.cr.fetchall()
assert not changed, f"Backfill changed pre-existing master or transaction rows: {changed}"
PY
}

operator dry-run | tee "$fixture/plan.log"
grep -F "mode=dry-run company=$company planned=2 preserved=0" "$fixture/plan.log"
verify 0

sed -i 's/CI-CARTON-2,CI-CARTON,Karton,120/CI-CARTON-2,CI-CARTON,Karton,121/' "$fixture/data/seed/products_150.csv"
if operator apply > "$fixture/invalid.log" 2>&1; then exit 1; fi
grep -F 'Carton conversion mismatch for SKU CI-CARTON-2' "$fixture/invalid.log"
verify 0
sed -i 's/CI-CARTON-2,CI-CARTON,Karton,121/CI-CARTON-2,CI-CARTON,Karton,120/' "$fixture/data/seed/products_150.csv"

shell <<'PY'
env.cr.execute("""
    CREATE FUNCTION ci_reject_second_offer() RETURNS trigger LANGUAGE plpgsql AS $$
    BEGIN
      IF (SELECT default_code FROM product_template WHERE id = NEW.product_tmpl_id) = 'CI-CARTON-2' THEN
        RAISE EXCEPTION 'CI forced failure on second carton offer';
      END IF;
      RETURN NEW;
    END $$;
    CREATE TRIGGER ci_reject_second_offer AFTER INSERT ON product_supplierinfo
    FOR EACH ROW EXECUTE FUNCTION ci_reject_second_offer();
""")
env.cr.commit()
PY
if operator apply > "$fixture/create-failure.log" 2>&1; then exit 1; fi
grep -F 'CI forced failure on second carton offer' "$fixture/create-failure.log"
verify 0
shell <<'PY'
env.cr.execute("DROP TRIGGER ci_reject_second_offer ON product_supplierinfo")
env.cr.commit()
PY

operator apply | tee "$fixture/apply.log"
grep -F "mode=apply company=$company planned=2 preserved=0" "$fixture/apply.log"
verify 2
operator apply | tee "$fixture/replay.log"
grep -F "mode=apply company=$company planned=0 preserved=2" "$fixture/replay.log"
verify 2
echo 'VENDOR_CARTON_BACKFILL_SHELL=PASS'
