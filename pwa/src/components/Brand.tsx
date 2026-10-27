export function Brand({ large = false }: { large?: boolean }) {
    return (
        <img
            class={`app-brand${large ? " large" : ""}`}
            src="/field/brand-logo.svg"
            width="300"
            height="118"
            alt="Odoo FMCG Mobile"
        />
    );
}
