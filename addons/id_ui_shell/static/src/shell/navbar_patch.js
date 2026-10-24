import { _t } from "@web/core/l10n/translation";
import { patch } from "@web/core/utils/patch";
import { NavBar } from "@web/webclient/navbar/navbar";
import { UserMenu } from "@web/webclient/user_menu/user_menu";
import { user } from "@web/core/user";
import { IdMenuSearch } from "./id_menu_search";

// Titik sentuh NavBar: mendaftarkan pencarian menu (template: navbar_patch.xml).
patch(NavBar, {
    components: { ...NavBar.components, IdMenuSearch },
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
