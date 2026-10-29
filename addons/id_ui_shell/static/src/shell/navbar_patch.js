import { onMounted, onWillUnmount, useRef } from "@odoo/owl";
import { _t } from "@web/core/l10n/translation";
import { patch } from "@web/core/utils/patch";
import { NavBar } from "@web/webclient/navbar/navbar";
import { UserMenu } from "@web/webclient/user_menu/user_menu";
import { user } from "@web/core/user";
import { IdMenuSearch } from "./id_menu_search";
import { observeSystrayDividers } from "./systray_dividers";

// Titik sentuh NavBar: mendaftarkan pencarian menu (template: navbar_patch.xml).
patch(NavBar, {
    components: { ...NavBar.components, IdMenuSearch },
});

// The template ref scopes observers to this navbar. Always disconnect on unmount.
patch(NavBar.prototype, {
    setup() {
        super.setup(...arguments);
        const tray = useRef("id_systray");
        let cleanup;
        onMounted(() => { if (tray.el) cleanup = observeSystrayDividers(tray.el); });
        onWillUnmount(() => cleanup?.());
    },
});

// Role di samping avatar. Placeholder sebelum id_app menyediakan role bisnis;
// addon lain dapat meng-override getter ini.
patch(UserMenu.prototype, {
    get idRoleLabel() {
        if (user.isAdmin) {
            return _t("Administrator");
        }
        return user.isInternalUser ? _t("User") : _t("Portal");
    },
});
