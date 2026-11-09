import { IconButton } from "./IconButton";

export type SheetHeaderProps = {
    title: string;
    /** id untuk aria-labelledby pada dialog. */
    titleId: string;
    eyebrow?: string;
    onClose: () => void;
    closeLabel?: string;
    closeDisabled?: boolean;
};

/** Kepala lembar/dialog: eyebrow, judul, dan tombol tutup 44 px. */
export function SheetHeader({
    title,
    titleId,
    eyebrow,
    onClose,
    closeLabel = "Tutup",
    closeDisabled,
}: SheetHeaderProps) {
    return (
        <header class="sheet-head">
            <div>
                {eyebrow ? <p class="eyebrow">{eyebrow}</p> : null}
                <h2 id={titleId}>{title}</h2>
            </div>
            <IconButton
                icon="close"
                label={closeLabel}
                onClick={onClose}
                disabled={closeDisabled}
            />
        </header>
    );
}
