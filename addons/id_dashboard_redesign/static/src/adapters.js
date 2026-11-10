/** @odoo-module **/
import { _t } from "@web/core/l10n/translation";
const fmt = (n, digits = 1) => Number.isFinite(n) ? new Intl.NumberFormat("id-ID", { maximumFractionDigits: digits }).format(n) : "—";
const formatMoney = (n, currency) => {
    if (!Number.isFinite(n)) return { num: "—", unit: "", cur: "" };
    const scale = Math.abs(n) >= 1e9 ? 1e9 : Math.abs(n) >= 1e6 ? 1e6 : 1;
    return { num: fmt(n / scale, 2), unit: scale === 1e9 ? _t("billion") : scale === 1e6 ? _t("million") : "", cur: currency };
};
const rate = (n, d) => d ? n / d : null;
const pct = n => Number.isFinite(n) ? n * 100 : null;
export function adaptSource(dashboard, response, scope = {}) {
    const raw = response.source, t = raw.total, prev = raw.previous;
    const money = n => formatMoney(n, raw.currency === "IDR" ? "Rp" : raw.currency);
    const card = (label, amount, options = {}) => ({
        label, ...(options.money ? money(amount) : { num: fmt(amount), unit: options.unit || "" }),
        txt: options.txt || "", icon: options.icon || "chart", good: true, spark: [], delta: "", ...options,
    });
    const value = {
        __available: {}, sub: _t("Confirmed sales orders · ex-tax · WITA"), role: scope.role_label,
        sync: response.read_at + " UTC", period: raw.period.start + " – " + raw.period.end,
        coverTitle: _t("City / regency coverage"), areaFoot: raw.currency + " " + _t("million. Map: North Sulawesi; ranking includes unassigned and out-of-map locations."),
        mapLegend: raw.currency + " " + _t("million"), mapHead: raw.currency + " " + _t("million") + " · %",
        mapCrumbs: [_t("North Sulawesi"), _t("City / regency")],
        config: { panel6: {}, panel7: {} }, cityDrills: {},
        revenueUnit: raw.currency + " " + _t("million / calendar day"),
        monthlyNote: raw.currency + " " + _t("billion; line: discount as % of gross SO") + " · " + _t("Five months through selected end date"),
    };
    for (let i = 0; i < 11; i++) value.__available[`D1.${i}`] = false;
    [0, 1, 2, 3, 4, 5, 6].forEach(i => value.__available[`D1.${i}`] = true);
    const ec = t.pjp?.available ? pct(t.pjp.ec_ratio) : null;
    const target = raw.target?.available ? pct(raw.target.achievement) : null;
    value.kpis = [
        card(_t("Gross SO (ex-tax)"), t.gross, { money: true }),
        card(_t("Posted refunds / gross SO"), raw.refund?.available ? pct(rate(raw.refund.amount, t.gross)) : null, {
            unit: "%", pre: raw.refund?.available ? money(raw.refund.amount).cur + " " + money(raw.refund.amount).num + " " + money(raw.refund.amount).unit : "",
            txt: _t("Refund invoice date; not a SO-cohort return rate"), drill: raw.refund?.drill }),
        card(_t("Net SO (ex-tax)"), t.net, { money: true, txt: _t("Gross less native line discount") }),
        card(_t("Target achievement"), target, { unit: "%", bar: target,
            pre: raw.target?.available ? money(t.net).cur + " " + money(t.net).num + " " + money(t.net).unit : "",
            good: raw.target?.available ? raw.target.achievement >= 1 : true,
            txt: raw.target?.available ? _t("Exact period and complete salesperson scope") : raw.target?.reason }),
        card(_t("Native SO discount"), pct(t.discount_ratio), { unit: "%", pre: money(t.discount).cur + " " + money(t.discount).num + " " + money(t.discount).unit }),
        card(_t("Effective call"), ec, { unit: "%", pre: t.pjp?.available ? fmt(t.pjp.effective, 0) + " " + _t("calls") : "", txt: t.pjp?.available ? `${t.pjp.effective} / ${t.pjp.visits}` : raw.pjp_status?.reason }),
        card(_t("Calls / assigned workday"), t.calls_per_day, { txt: _t("Accepted visits / readable assigned salesperson-days") }),
        card(_t("Average SO value"), t.aov, { money: true }),
    ];
    ["chart", "undo", "wallet", "target", "pct", "phone", "clock", "cart"].forEach((icon, i) => value.kpis[i].icon = icon);
    value.kpis[0].spark = raw.trend.map(p => p.gross);
    value.kpis[1].spark = raw.refund?.trend || [];
    value.kpis[2].spark = raw.trend.map(p => p.net);
    value.kpis[4].spark = raw.trend.filter(p => p.gross).map(p => p.discount / p.gross * 100);
    value.kpis[7].spark = raw.trend.filter(p => p.orders).map(p => p.net / p.orders);
    if (raw.target?.available) {
        let accumulated = 0;
        value.kpis[3].spark = raw.trend.map(p => (accumulated += p.net) / raw.target.amount * 100);
    }
    for (const [index, key] of [[0, "gross"], [2, "net"], [7, "aov"]]) {
        const before = key === "aov" ? rate(prev?.net, prev?.orders) : prev?.[key];
        if (Number.isFinite(before) && before !== 0) {
            const delta = (t[key] - before) / Math.abs(before) * 100;
            value.kpis[index].delta = (delta >= 0 ? "+" : "") + fmt(delta) + "%";
            value.kpis[index].good = delta >= 0;
        }
        value.kpis[index].drill = { model: "sale.order.line", domain: raw.line_domain };
    }
    const bars = rows => rows.map(r => ({ n: r.name, v: r.net / 1e6, t: fmt(r.net / 1e6) + " · " + fmt((rate(r.net, t.net) ?? NaN) * 100) + "%", drill: r.drill }));
    value.principal = bars(raw.principal);
    value.channel = bars(raw.channel);
    value.area = bars(raw.city);
    value.areaVals = {};
    for (const row of raw.city) if (row.code) {
        value.areaVals[row.code] = row.net / 1e6;
        value.cityDrills[row.code] = row.drill;
    }
    value.trend = [{ v: raw.trend.map(r => r.net / 1e6) }];
    value.trendLegend = [{ t: _t("Selected period"), c: "var(--ac)" }];
    if (raw.previous_trend) {
        value.trend.push({ v: raw.previous_trend.slice(0, raw.trend.length).map(r => r.net / 1e6) });
        value.trendLegend.push({ t: raw.previous_period.start + " – " + raw.previous_period.end, c: "var(--ac2)", d: true });
    }
    const points = value.trend.flatMap(s => s.v);
    const low = Math.min(0, ...points), high = Math.max(1, ...points);
    value.config.panel6 = { min: low, max: high, target: undefined };
    value.trendTicks = [low, (low + high) / 2, high].map(n => Math.round(n * 10) / 10);
    value.trendX = raw.trend.map((r, i) => i % Math.ceil(raw.trend.length / 7) === 0 || i === raw.trend.length - 1 ? r.date.slice(5) : "");
    value.mBars = raw.monthly.map(r => ({ l: r.month, v: r.net / 1e9, t: fmt(r.net / 1e9, 2), drill: r.drill }));
    value.mLine = raw.monthly.map(r => ({ v: pct(r.discount_ratio), t: fmt(pct(r.discount_ratio)) + "%" }));
    value.config.panel7 = { barMax: Math.max(.001, ...value.mBars.map(r => Math.abs(r.v))),
        lineMin: Math.min(0, ...value.mLine.map(r => r.v).filter(Number.isFinite)), lineMax: Math.max(1, ...value.mLine.map(r => r.v).filter(Number.isFinite)) };
    value.tcols = [{ h: "#", w: "28px" }, { h: _t("Salesperson"), w: "1.4fr" },
        { h: _t("Sales team"), w: "1fr" }, { h: _t("Net SO (million)"), w: "1.5fr" },
        { h: _t("Achievement"), w: "80px" }, { h: _t("EC %"), w: "65px" }, { h: _t("Active outlets"), w: "80px" }];
    const maxSales = Math.max(1, ...raw.salesmen.map(r => Math.abs(r.net)));
    value.trows = raw.salesmen.slice(0, 8).map((r, index) => [index + 1, { t: r.name, drill: r.drill, b: true },
        (r.teams || []).join(", ") || "—", { t: fmt(r.net / 1e6), bar: Math.abs(r.net) / maxSales * 100 },
        fmt(pct(r.achievement)) + "%", fmt(r.pjp?.available ? pct(r.pjp.ec_ratio) : null), fmt(r.outlets, 0)]);
    value.sp = raw.salesmen.filter(r => Number.isFinite(r.calls_per_day)).map(r => ({
        x: r.calls_per_day, y: r.net / 1e6, r: Math.min(36, 8 + Math.sqrt(r.outlets) * 2), l: r.name, drill: r.drill,
    }));
    value.__available["D1.7"] = value.sp.length > 0;
    value.spx = [0, Math.max(1, ...value.sp.map(r => r.x)) * 1.2];
    value.spy = [Math.min(0, ...value.sp.map(r => r.y)), Math.max(1, ...value.sp.map(r => r.y)) * 1.2];
    value.spxt = value.spx.map(n => Math.round(n * 10) / 10);
    value.spyt = value.spy.map(n => Math.round(n * 10) / 10);
    return value;
}
