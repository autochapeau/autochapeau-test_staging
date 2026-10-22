/** @odoo-module **/

import { EventBus } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { ZiwoSystrayItem } from "./ziwo_systray_item";
import { DialingPanel } from "./dialing_panel";

const systrayRegistry = registry.category("systray");
const mainComponentRegistry = registry.category("main_components");

export const bus = new EventBus();

export const ziwoService = {
    dependencies: ["user", "notification"],
    async start(env, { user, notification }) {
        const isEmployee = await user.hasGroup('base.group_user');
        if (isEmployee && window.innerWidth > 767) {
            systrayRegistry.add('forge_ziwo', { Component: ZiwoSystrayItem, props: { bus } });
            mainComponentRegistry.add('forge_ziwo.DialingPanel', {
                Component: DialingPanel,
                props: { bus },
            });
        }
    },
};