import { Icon, type IconName } from "../components/Icon";

export type BottomNavItem = {
    id: string;
    name: string;
    icon: IconName;
    /** Kelas aktif (tab terpilih menyatu dengan latar halaman). */
    active: boolean;
    /** aria-current="page"; boleh berbeda dari active untuk halaman turunan. */
    current: boolean;
    /** Titik penanda ada item menunggu. */
    dot?: boolean;
};

/** Navigasi utama bawah. Markup dan kelas sama dengan .bottom-nav di style.css. */
export function BottomNav({
    items,
    onSelect,
    label = "Navigasi utama",
}: {
    items: BottomNavItem[];
    onSelect: (id: string) => void;
    label?: string;
}) {
    return (
        <nav class="bottom-nav" aria-label={label}>
            {items.map((item) => (
                <button
                    key={item.id}
                    type="button"
                    class={item.active ? "active" : ""}
                    aria-current={item.current ? "page" : undefined}
                    onClick={() => onSelect(item.id)}
                >
                    <span class="nav-icon">
                        <Icon name={item.icon} size={24} />
                        {item.dot ? <span class="nav-dot" /> : null}
                    </span>
                    <span>{item.name}</span>
                </button>
            ))}
        </nav>
    );
}
