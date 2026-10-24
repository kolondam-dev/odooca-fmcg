import { patch } from "@web/core/utils/patch";
import { WebClient } from "@web/webclient/webclient";
import { IdSidebar } from "./id_sidebar";

// Satu-satunya titik sentuh ke WebClient: mendaftarkan komponen sidebar.
// Template-nya disisipkan oleh webclient_patch.xml.
patch(WebClient, {
    components: { ...WebClient.components, IdSidebar },
});
