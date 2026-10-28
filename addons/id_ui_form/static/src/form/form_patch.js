import { onMounted, onPatched, onWillDestroy, onWillUnmount, useRef, useState, useSubEnv } from "@odoo/owl";
import { _t } from "@web/core/l10n/translation";
import { Notebook } from "@web/core/notebook/notebook";
import { useService } from "@web/core/utils/hooks";
import { patch } from "@web/core/utils/patch";
import { FormRenderer } from "@web/views/form/form_renderer";
import { IdChatterPage } from "./id_chatter_page";

/**
 * Tata letak sidebar: chatter pindah dari samping/bawah form menjadi tab terakhir
 * di notebook terluar. Kompatibilitas:
 *  - tidak mengubah addon mail; chatter bawaan disembunyikan lewat mailLayout() = "NONE"
 *    (nilai yang sudah dikenal kompiler form) dan dirender ulang di dalam tab;
 *  - bila form tidak punya notebook, ada pratinjau lampiran, atau notebook tak pernah
 *    muncul, tata letak chatter bawaan dipakai kembali.
 *  - judul murni (nomor/nama dokumen) ditampilkan ulang di tengah statusbar, tepat di antara
 *    tombol aksi dan pipeline status. Field tidak pernah dipindah: blok judul yang berisi
 *    field untuk diisi pengguna (mis. kendaraan, produk) tetap di tempatnya.
 */
/**
 * Membaca judul yang aman dipromosikan ke statusbar.
 * Judul readonly boleh berupa teks biasa. Satu-satunya kontrol editable yang didukung
 * adalah satu input teks non-wajib di dalam h1 (nomor draft faktur). Semua bentuk lain
 * ditolak agar blok asli tetap terlihat dan field pengguna tidak pernah tersembunyi.
 */
/**
 * Mengembalikan satu-satunya input editable yang memang didukung untuk judul.
 * Hidden input diabaikan; semua kontrol visible harus lolos guard yang sama untuk
 * rendering dan aktivasi tombol agar keduanya tidak pernah memilih field berbeda.
 */
export function getEditableTitleInput(block) {
    if (!block) {
        return null;
    }
    const controls = [...block.querySelectorAll(
        'input:not([type="hidden"]), select, textarea, [contenteditable]:not([contenteditable="false"])'
    )];
    if (controls.length !== 1) {
        return null;
    }
    const [input] = controls;
    const type = (input.getAttribute("type") || "text").toLowerCase();
    if (
        input.tagName !== "INPUT" ||
        !input.closest("h1") ||
        !["text", "search"].includes(type) ||
        input.required ||
        input.getAttribute("aria-required") === "true" ||
        input.closest('[aria-required="true"]') ||
        input.closest(".o_required_modifier") ||
        input.readOnly ||
        input.disabled
    ) {
        return null;
    }
    return input;
}

/**
 * Membuka editor hanya melalui input visible yang telah lolos guard.
 * Fungsi ini dipakai langsung oleh handler dan diuji terhadap fixture DOM.
 */
export function focusEditableTitleInput(block) {
    const input = getEditableTitleInput(block);
    if (!block || !input) {
        return null;
    }
    block.classList.add("id_title_editing");
    input.focus();
    return input;
}

/**
 * Membaca judul yang aman dipromosikan ke statusbar. Judul readonly boleh berupa teks
 * biasa; kontrol editable hanya diterima jika getEditableTitleInput mengembalikan input
 * teks/pencarian non-wajib yang tunggal. Jika ada kontrol visible tidak didukung, blok asli
 * tetap terlihat.
 */
export function readTitleSpec(block) {
    if (!block) {
        return null;
    }
    const controls = [...block.querySelectorAll(
        'input:not([type="hidden"]), select, textarea, [contenteditable]:not([contenteditable="false"])'
    )];
    const input = controls.length ? getEditableTitleInput(block) : null;
    if (controls.length && !input) {
        return null;
    }
    const h1 = block.querySelector("h1");
    if (!h1 || h1.querySelectorAll("h1").length) {
        return null;
    }
    const main = (input ? input.value || input.placeholder : h1.textContent || "").trim();
    if (!main) {
        return null;
    }
    const caption = [...block.querySelectorAll(".o_form_label")]
        .filter((el) => !el.closest("h1"))
        .map((el) => el.textContent.trim())
        .filter(Boolean)
        .join(" ");
    return { main, caption, editable: Boolean(input) };
}

patch(FormRenderer.prototype, {
    setup() {
        super.setup();
        const shell = useService("id_shell");
        const ui = useService("ui");
        this.idShellState = useState(shell.state);
        this.idUi = useState(ui);
        this.idChatterFallback = useState({ value: false });
        const tab = {
            owner: null,
            get enabled() {
                return this.renderer.idChatterTabEnabled;
            },
            getProps: () => this.idChatterProps(),
            renderer: this,
        };
        this.idChatterTab = tab;
        useSubEnv({ idChatterTab: tab });

        // Judul murni ditampilkan ulang di tengah statusbar lewat elemen milik kita sendiri
        // (.id_header_title); node OWL tidak pernah dipindah. Dibatasi ke akar renderer ini,
        // idempoten (tidak menyentuh DOM bila teks tidak berubah), dan dibuang bila tata letak
        // klasik atau form di dialog. Blok asli di sheet disembunyikan lewat CSS (:has).
        const rootRef = useRef("compiled_view_root");
        const syncTitle = () => {
            const root = rootRef.el;
            if (!root) {
                return;
            }
            const statusbar = root.querySelector(".o_form_statusbar");
            const block = root.querySelector(".o_form_sheet > .oe_title");
            const current = statusbar?.querySelector(":scope > .id_header_title");
            // Syarat sama dengan CSS (body.id-shell-sidebar): sidebar aktif dan layar bukan kecil.
            const active = this.idShellState?.mode === "sidebar" && !this.idUi?.isSmall && !this.env.inDialog;
            const spec = active && statusbar && block ? readTitleSpec(block) : null;
            if (!spec) {
                current?.remove();
                return;
            }
            const key = `${spec.caption}\u0000${spec.main}\u0000${spec.editable}`;
            if (current?.dataset.idKey === key) {
                return;
            }
            let header = current;
            let needsInsert = !current;
            let needsListener = !current && spec.editable;
            if (!header || (spec.editable && header.tagName !== "BUTTON") || (!spec.editable && header.tagName === "BUTTON")) {
                const replacement = document.createElement(spec.editable ? "button" : "div");
                if (header) {
                    header.replaceWith(replacement);
                }
                header = replacement;
                needsInsert = !header.isConnected;
                needsListener = spec.editable;
            }
            header.className = "id_header_title" + (spec.editable ? " id_header_title--editable" : "");
            header.dataset.idKey = key;
            if (spec.editable) {
                header.type = "button";
                header.setAttribute("aria-label", `${_t("Edit document number")}: ${spec.main}`);
            } else {
                header.removeAttribute("type");
                header.removeAttribute("aria-label");
            }
            const parts = [];
            if (spec.caption) {
                const caption = document.createElement("span");
                caption.className = "id_header_title__caption";
                caption.textContent = spec.caption;
                parts.push(caption);
            }
            const main = document.createElement("span");
            main.className = "id_header_title__main";
            main.textContent = spec.main;
            parts.push(main);
            header.replaceChildren(...parts);
            if (needsListener) {
                header.addEventListener("click", onTitleClick);
            }
            if (needsInsert) {
                // Sisipkan sebelum anak langsung statusbar yang memuat pipeline status (bila ada).
                let ref = statusbar.querySelector(".o_field_statusbar, .o_statusbar_status");
                while (ref && ref.parentNode !== statusbar) {
                    ref = ref.parentNode;
                }
                statusbar.insertBefore(header, ref || null);
            }
        };
        // Tombol native menyediakan Tab, Enter, Space, dan semantik aksesibilitas.
        // Field OWL asli tetap berada di sheet; hanya dibuka sementara untuk diedit.
        const onTitleClick = () => {
            const block = rootRef.el?.querySelector(".o_form_sheet > .oe_title");
            const input = getEditableTitleInput(block);
            if (!block || !input) {
                return;
            }
            const closeEditor = () => {
                block.classList.remove("id_title_editing");
                input.removeEventListener("keydown", onEditorKeydown);
                syncTitle();
            };
            const onEditorKeydown = (ev) => {
                if (ev.key === "Escape") {
                    ev.preventDefault();
                    input.blur();
                    rootRef.el?.querySelector(".o_form_statusbar > .id_header_title")?.focus();
                }
            };
            input.addEventListener("blur", closeEditor, { once: true });
            input.addEventListener("keydown", onEditorKeydown);
            // Revalidasi saat aktivasi; hidden input tak pernah dapat menerima fokus.
            if (focusEditableTitleInput(block) !== input) {
                input.removeEventListener("blur", closeEditor);
                input.removeEventListener("keydown", onEditorKeydown);
            }
        };
        // Ketikan di input judul langsung tercermin di header.
        const onInput = (ev) => {
            if (ev.target.closest?.(".o_form_sheet > .oe_title")) {
                syncTitle();
            }
        };

        onMounted(() => {
            if (this.idChatterTabEnabled && !tab.owner) {
                this.idChatterFallback.value = true;
            }
            rootRef.el?.addEventListener("input", onInput);
            syncTitle();
        });
        onWillUnmount(() => rootRef.el?.removeEventListener("input", onInput));
        onPatched(syncTitle);
    },

    get idChatterTabEnabled() {
        if (
            this.idChatterFallback?.value ||
            this.idShellState?.mode !== "sidebar" ||
            this.idUi?.isSmall ||
            !this.mailStore ||
            this.env.inDialog
        ) {
            return false;
        }
        const xmlDoc = this.props.archInfo?.xmlDoc;
        return Boolean(xmlDoc && xmlDoc.querySelector("chatter") && xmlDoc.querySelector("notebook"));
    },

    idChatterProps() {
        const { record, archInfo } = this.props;
        return {
            chatter: {
                has_activities: archInfo.has_activities,
                hasAttachmentPreview: false,
                threadId: record.resId || undefined,
                threadModel: record.resModel,
                record,
                saveRecord: this.props.saveRecord,
                highlightMessageId: this.highlightMessageId,
                isChatterAside: false,
                isInFormSheetBg: false,
            },
        };
    },

    mailLayout(hasAttachmentContainer) {
        // Pratinjau lampiran (mis. tagihan vendor) tetap memakai tata letak bawaan.
        if (this.idChatterTabEnabled && !(hasAttachmentContainer && this.hasFile())) {
            return "NONE";
        }
        return super.mailLayout(hasAttachmentContainer);
    },
});

patch(Notebook.prototype, {
    setup() {
        super.setup();
        onWillDestroy(() => {
            const tab = this.env.idChatterTab;
            if (tab && tab.owner === this) {
                tab.owner = null;
            }
        });
    },

    computePages(props) {
        const pages = super.computePages(props);
        const tab = this.env.idChatterTab;
        if (tab && pages.length && tab.enabled && (!tab.owner || tab.owner === this)) {
            tab.owner = this; // notebook terluar (terbentuk pertama) memiliki tab chatter
            pages.push([
                "id_chatter",
                {
                    id: "id_chatter",
                    name: "id_chatter",
                    title: _t("Messages & Activities"),
                    isVisible: true,
                    Component: IdChatterPage,
                    props: tab.getProps(),
                },
            ]);
        }
        return pages;
    },
});
