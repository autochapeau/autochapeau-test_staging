/** @odoo-module **/
import { Component, useState } from '@odoo/owl';
import { useHotkey } from '@web/core/hotkeys/hotkey_hook';
import { useBus, useService } from '@web/core/utils/hooks';
import { registry } from '@web/core/registry';

export const COMMISSION_APP = 'sales_region_commission.menu_root';
const icons = {
    menu_dashboard: 'fa-th-large', menu_ledger: 'fa-list-alt', menu_targets: 'fa-bullseye',
    menu_rules: 'fa-sliders', menu_teams: 'fa-sitemap', menu_calculate: 'fa-calculator',
    menu_service_category: 'fa-tags', menu_accounting_settings: 'fa-university',
    menu_user_access: 'fa-user-circle-o', menu_guide: 'fa-book',
};
export function commissionMenus(menu) {
    const root = menu.getApps().find(app => app.xmlid === COMMISSION_APP);
    return root ? menu.getMenuAsTree(root.id).childrenTree : [];
}
export function menuIcon(item) { return 'fa ' + (icons[item.xmlid?.split('.').pop()] || 'fa-circle-o'); }

export class CommissionNavigation extends Component {
    static template = 'sales_region_commission.Navigation';
    setup() {
        this.menu = useService('menu');
        this.action = useService('action');
        this.router = useService('router');
        this.state = useState({ revision: 0, collapsed: false, mobileOpen: false, busy: false });
        for (const event of ['MENUS:APP-CHANGED', 'ACTION_MANAGER:UI-UPDATED', 'ROUTE_CHANGE']) {
            useBus(this.env.bus, event, () => { this.state.revision++; });
        }
        useHotkey('escape', () => this.state.mobileOpen = false, { global: true, isAvailable: () => this.active && this.state.mobileOpen });
    }
    get active() { this.state.revision; return this.menu.getCurrentApp()?.xmlid === COMMISSION_APP; }
    get items() { return commissionMenus(this.menu); }
    get workItems() { return this.items.filter(item => ['menu_dashboard','menu_ledger','menu_targets','menu_rules'].includes(item.xmlid.split('.').pop())); }
    get adminItems() { return this.items.filter(item => !this.workItems.includes(item) && item.xmlid !== 'sales_region_commission.menu_guide'); }
    get guide() { return this.items.find(item => item.xmlid === 'sales_region_commission.menu_guide'); }
    icon(item) { return menuIcon(item); }
    selected(item) {
        const action = this.action.currentController?.action;
        if (action?.id) return String(item.actionID) === String(action.id);
        return action?.res_model === 'sales.commission.entry' && item.xmlid === 'sales_region_commission.menu_ledger';
    }
    async navigate(item) {
        if (this.state.busy) return;
        this.state.busy = true;
        try { await this.menu.selectMenu(item); this.state.mobileOpen = false; this.state.revision++; }
        finally { this.state.busy = false; }
    }
    toggle() {
        if (window.matchMedia('(max-width: 900px)').matches) this.state.mobileOpen = !this.state.mobileOpen;
        else this.state.collapsed = !this.state.collapsed;
    }
}
registry.category('main_components').add('sales_region_commission.Navigation', { Component: CommissionNavigation });
