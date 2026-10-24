import { Component } from "@odoo/owl";
import { Chatter } from "@mail/chatter/web_portal/chatter";

/** Isi tab "Pesan & Aktivitas": membungkus Chatter bawaan mail dengan props yang sama seperti kompiler form. */
export class IdChatterPage extends Component {
    static template = "id_ui_form.ChatterPage";
    static components = { Chatter };
    static props = { chatter: Object };
}
