/** Mark visible direct systray items without overriding their native display rules. */
export function observeSystrayDividers(tray) {
    let frame = 0;
    let stopped = false;
    const observed = new Set();
    const sync = () => {
        frame = 0;
        if (stopped) return;
        const children = [...tray.children];
        for (const child of observed) {
            if (child.parentElement !== tray) {
                resize.unobserve(child);
                observed.delete(child);
            }
        }
        let previous = false;
        for (const child of children) {
            if (!observed.has(child)) {
                resize.observe(child);
                observed.add(child);
            }
            const style = getComputedStyle(child);
            const visible = child.getBoundingClientRect().width > 0 &&
                child.getBoundingClientRect().height > 0 &&
                !["hidden", "collapse"].includes(style.visibility) &&
                !child.matches(":empty") && !child.querySelector(":scope > .o_mobile_menu_toggle");
            child.classList.toggle("id_systray_item", visible);
            child.classList.toggle("id_systray_divider", visible && previous);
            if (visible) previous = true;
        }
    };
    const schedule = () => {
        if (!stopped && !frame) frame = requestAnimationFrame(sync);
    };
    const resize = new ResizeObserver(schedule);
    const mutations = new MutationObserver(schedule);
    mutations.observe(tray, { childList: true, subtree: true, attributes: true,
        attributeFilter: ["class", "style", "hidden"] });
    resize.observe(tray);
    window.addEventListener("resize", schedule);
    sync();
    return () => {
        stopped = true;
        cancelAnimationFrame(frame);
        mutations.disconnect();
        resize.disconnect();
        window.removeEventListener("resize", schedule);
        for (const child of tray.children) {
            child.classList.remove("id_systray_item", "id_systray_divider");
        }
    };
}
