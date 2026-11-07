import { describe, expect, it } from "vitest";
import type { ComponentChildren, VNode } from "preact";
import {
    BottomNav,
    Button,
    Checkbox,
    Chip,
    Field,
    IconButton,
    Progress,
    RadioRow,
    Segmented,
    SheetHeader,
    Textarea,
    StatusDot,
    Stepper,
    clamp,
    cx,
    stepValue,
} from "../src/ui";

type Props = Record<string, unknown> & { children?: ComponentChildren };

/** Render vnode menjadi teks sederhana: cukup untuk menguji struktur dan atribut tanpa DOM. */
function html(node: ComponentChildren): string {
    if (node === null || node === undefined || typeof node === "boolean")
        return "";
    if (typeof node === "string" || typeof node === "number")
        return String(node);
    if (Array.isArray(node)) return node.map(html).join("");
    const vnode = node as VNode<Props>;
    const props = vnode.props ?? {};
    if (typeof vnode.type === "function") {
        return html((vnode.type as (p: Props) => ComponentChildren)(props));
    }
    if (props.dangerouslySetInnerHTML) return "<icon/>";
    const attrs = Object.entries(props)
        .filter(
            ([key, value]) =>
                key !== "children" &&
                !key.startsWith("on") &&
                key !== "style" &&
                value !== undefined &&
                (value !== false || key.startsWith("aria-")) &&
                value !== null,
        )
        .map(([key, value]) =>
            value === true && !key.startsWith("aria-")
                ? key
                : `${key}="${value}"`,
        )
        .join(" ");
    return `<${vnode.type} ${attrs}>${html(props.children)}</${vnode.type}>`;
}

describe("helper", () => {
    it("cx membuang nilai falsy", () => {
        expect(cx("a", false, undefined, null, "b")).toBe("a b");
    });
    it("clamp dan stepValue menjaga rentang", () => {
        expect(clamp(5, 0, 3)).toBe(3);
        expect(clamp(-1, 0, 3)).toBe(0);
        expect(stepValue(3, 1, 0, 3)).toBe(3);
        expect(stepValue(0, -1, 0, 3)).toBe(0);
        expect(stepValue(2, 1, 0, 3)).toBe(3);
    });
});

describe("Button", () => {
    it("default tombol utama 56 px dengan type=button", () => {
        const out = html(Button({ children: "Simpan" }));
        expect(out).toContain('type="button"');
        expect(out).toContain("ui-btn ui-btn--pri ui-btn--lg");
    });
    it("nonaktif memakai atribut disabled asli", () => {
        expect(html(Button({ disabled: true, children: "x" }))).toContain(
            " disabled",
        );
    });
    it("varian, ukuran, ikon, dan lebar otomatis", () => {
        const out = html(
            Button({
                variant: "sec",
                size: "sm",
                icon: "check",
                auto: true,
                children: "x",
            }),
        );
        expect(out).toContain("ui-btn--sec ui-btn--sm ui-btn--auto");
        expect(out).toContain("<icon/>");
    });
});

describe("IconButton", () => {
    it("selalu punya aria-label dan lencana hanya bila > 0", () => {
        const out = html(
            IconButton({ icon: "bell", label: "Notifikasi", badge: 3 }),
        );
        expect(out).toContain('aria-label="Notifikasi"');
        expect(out).toContain(">3<");
        expect(
            html(IconButton({ icon: "bell", label: "N", badge: 0 })),
        ).not.toContain("ui-iconbtn__badge");
    });
});

describe("Chip", () => {
    it("tone menentukan kelas", () => {
        expect(html(Chip({ tone: "bad", children: "Gagal" }))).toContain(
            "ui-chip--bad",
        );
        expect(html(Chip({ children: "x" }))).toContain("ui-chip--neu");
    });
});

describe("Field", () => {
    it("galat menandai aria-invalid dan role=alert", () => {
        const out = html(Field({ label: "Referensi", error: "Wajib diisi" }));
        expect(out).toContain('aria-invalid="true"');
        expect(out).toContain('role="alert"');
    });
    it("tanpa galat tidak ada aria-invalid; hint tampil", () => {
        const out = html(Field({ label: "Nama", hint: "Sesuai KTP" }));
        expect(out).not.toContain("aria-invalid");
        expect(out).toContain("Sesuai KTP");
    });
});

describe("Segmented", () => {
    it("hanya item terpilih yang aria-pressed", () => {
        const out = html(
            Segmented({
                label: "Metode",
                value: "giro",
                onChange: () => undefined,
                items: [
                    { value: "tunai", label: "Tunai" },
                    { value: "giro", label: "Giro" },
                ],
            }),
        );
        expect(out).toContain('role="group"');
        expect(out.match(/aria-pressed="true"/g)).toHaveLength(1);
        expect(out).toContain('aria-pressed="false"');
    });
});

describe("Checkbox dan RadioRow", () => {
    it("checkbox tanpa teks memakai label sebagai aria-label", () => {
        const out = html(
            Checkbox({
                checked: true,
                onChange: () => undefined,
                label: "Pilih faktur",
            }),
        );
        expect(out).toContain('aria-label="Pilih faktur"');
        expect(out).toContain("checked");
    });
    it("radio terpilih diberi is-on", () => {
        const out = html(
            RadioRow({
                name: "alasan",
                value: "tutup",
                selected: true,
                onSelect: () => undefined,
                label: "Toko tutup",
            }),
        );
        expect(out).toContain("ui-radio is-on");
    });
});

describe("Stepper", () => {
    it("tombol nonaktif di batas", () => {
        const atMin = html(
            Stepper({ value: 0, onChange: () => undefined, max: 3 }),
        );
        expect(atMin).toMatch(
            /aria-label="Kurangi"[^>]*disabled|disabled[^>]*aria-label="Kurangi"/,
        );
        const atMax = html(
            Stepper({
                value: 3,
                onChange: () => undefined,
                max: 3,
                unit: "karton",
            }),
        );
        expect(atMax).toContain('aria-label="Tambah karton"');
        expect(atMax).toMatch(
            /aria-label="Tambah karton"[^>]*disabled|disabled[^>]*aria-label="Tambah karton"/,
        );
    });
});

describe("Progress dan StatusDot", () => {
    it("progress dijepit 0–100 dengan nilai ARIA", () => {
        const out = html(Progress({ value: 140, label: "Kunjungan" }));
        expect(out).toContain('aria-valuenow="100"');
        expect(html(Progress({ value: -5, label: "x" }))).toContain(
            'aria-valuenow="0"',
        );
    });
    it("titik status punya nama aksesibel", () => {
        expect(html(StatusDot({ online: false }))).toContain(
            'aria-label="Offline"',
        );
        expect(html(StatusDot({ online: true }))).toContain(
            'aria-label="Online"',
        );
    });
});

describe("BottomNav", () => {
    it("aktif dan aria-current dapat berbeda; titik hanya bila dot", () => {
        const out = html(
            BottomNav({
                onSelect: () => undefined,
                items: [
                    {
                        id: "sales",
                        name: "Sales",
                        icon: "store",
                        active: true,
                        current: false,
                    },
                    {
                        id: "more",
                        name: "Lainnya",
                        icon: "grid",
                        active: false,
                        current: false,
                        dot: true,
                    },
                ],
            }),
        );
        expect(out).toContain('aria-label="Navigasi utama"');
        expect(out.match(/class="active"/g)).toHaveLength(1);
        expect(out).not.toContain("aria-current");
        expect(out.match(/nav-dot/g)).toHaveLength(1);
    });
});

describe("SheetHeader", () => {
    it("menampilkan judul, eyebrow, dan tombol tutup berlabel", () => {
        const out = html(
            SheetHeader({
                title: "Order",
                titleId: "t",
                eyebrow: "Outlet A",
                onClose: () => {},
                closeLabel: "Tutup form",
            }),
        );
        expect(out).toContain("Outlet A");
        expect(out).toContain('id="t"');
        expect(out).toContain('aria-label="Tutup form"');
    });
});

describe("Textarea & Segmented disabled", () => {
    it("merender textarea berlabel dan item segmented nonaktif", () => {
        expect(
            html(Textarea({ label: "Catatan", value: "x", onInput: () => {} })),
        ).toContain("Catatan");
        expect(
            html(
                Segmented({
                    label: "T",
                    value: "a",
                    onChange: () => {},
                    items: [
                        { value: "a", label: "A" },
                        { value: "b", label: "B", disabled: true },
                    ],
                }),
            ),
        ).toContain("disabled");
    });
});
