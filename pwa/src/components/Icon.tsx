import house from "@phosphor-icons/core/assets/duotone/house-duotone.svg?raw";
import store from "@phosphor-icons/core/assets/duotone/storefront-duotone.svg?raw";
import truck from "@phosphor-icons/core/assets/duotone/truck-duotone.svg?raw";
import user from "@phosphor-icons/core/assets/duotone/user-circle-duotone.svg?raw";
import grid from "@phosphor-icons/core/assets/duotone/squares-four-duotone.svg?raw";
import sync from "@phosphor-icons/core/assets/duotone/arrows-clockwise-duotone.svg?raw";
import pin from "@phosphor-icons/core/assets/duotone/map-pin-duotone.svg?raw";
import camera from "@phosphor-icons/core/assets/duotone/camera-duotone.svg?raw";
import receipt from "@phosphor-icons/core/assets/duotone/receipt-duotone.svg?raw";
import wallet from "@phosphor-icons/core/assets/duotone/wallet-duotone.svg?raw";
import clock from "@phosphor-icons/core/assets/duotone/clock-duotone.svg?raw";
import arrow from "@phosphor-icons/core/assets/duotone/arrow-up-right-duotone.svg?raw";
import check from "@phosphor-icons/core/assets/duotone/check-circle-duotone.svg?raw";
import bell from "@phosphor-icons/core/assets/duotone/bell-duotone.svg?raw";
import caret from "@phosphor-icons/core/assets/duotone/caret-right-duotone.svg?raw";
import close from "@phosphor-icons/core/assets/duotone/x-duotone.svg?raw";
import bag from "@phosphor-icons/core/assets/duotone/shopping-bag-duotone.svg?raw";
import warning from "@phosphor-icons/core/assets/duotone/warning-circle-duotone.svg?raw";
import signal from "@phosphor-icons/core/assets/duotone/wifi-high-duotone.svg?raw";
import gas from "@phosphor-icons/core/assets/duotone/gas-pump-duotone.svg?raw";
const icons = {
    house,
    store,
    truck,
    user,
    grid,
    sync,
    pin,
    camera,
    receipt,
    wallet,
    clock,
    arrow,
    check,
    bell,
    caret,
    close,
    bag,
    warning,
    signal,
    gas,
};
export type IconName = keyof typeof icons;
// Only trusted, build-time Phosphor SVGs enter this wrapper. No server/user SVG.
export function Icon({ name, size = 24 }: { name: IconName; size?: number }) {
    return (
        <span
            class="icon"
            aria-hidden="true"
            style={{ width: `${size}px`, height: `${size}px` }}
            dangerouslySetInnerHTML={{ __html: icons[name] }}
        />
    );
}
