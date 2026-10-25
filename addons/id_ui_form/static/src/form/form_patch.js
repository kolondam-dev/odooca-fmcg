import { onMounted, onPatched, onWillDestroy, useState, useSubEnv } from "@odoo/owl";
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
 *  - judul form (.oe_title) dipindah ke tengah statusbar di antara tombol aksi dan pipeline.
 */
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

        const relocateTitle = () => {
            if (this.idShellState?.mode !== "sidebar" || this.env.inDialog) {
                return;
            }
            const rendererEl = document.querySelector(".o_action_manager .o_form_renderer");
            if (!rendererEl) return;
            const statusbar = rendererEl.querySelector(".o_form_statusbar");
            const title = rendererEl.querySelector(".o_form_sheet > .oe_title");
            if (statusbar && title) {
                title.classList.add("id_statusbar_title");
                const status = statusbar.querySelector(".o_field_statusbar, .o_statusbar_status");
                if (status) {
                    statusbar.insertBefore(title, status);
                } else {
                    statusbar.appendChild(title);
                }
            }
        };

        onMounted(() => {
            if (this.idChatterTabEnabled && !tab.owner) {
                this.idChatterFallback.value = true;
            }
            relocateTitle();
        });
        onPatched(relocateTitle);
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
