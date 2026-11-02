/** @odoo-module **/
import { Component, onWillStart, useState } from '@odoo/owl';
import { registry } from '@web/core/registry';
import { useService } from '@web/core/utils/hooks';
import { _t } from '@web/core/l10n/translation';

export class CommissionDashboard extends Component {
    static template = 'sales_region_commission.Dashboard';
    setup() {
        this.orm = useService('orm');
        this.action = useService('action');
        this.user = useService('user');
        const now = new Date();
        this.state = useState({ month: `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}`, team: '', loading: true, error: '', data: null, admin: false });
        this.request = 0;
        onWillStart(async () => {
            this.state.admin = await this.user.hasGroup('sales_region_commission.group_admin');
            await this.load();
        });
    }
    async load() {
        const request = ++this.request;
        this.state.loading = true;
        this.state.error = '';
        try {
            const data = await this.orm.call('sales.commission.entry', 'dashboard', [], { month: `${this.state.month}-01`, team_id: this.state.team ? Number(this.state.team) : false });
            if (request === this.request) this.state.data = data;
        } catch (error) {
            if (request === this.request) {
                this.state.data = null;
                this.state.error = _t('The dashboard could not be loaded. Refresh or check your access with an administrator.');
            }
        } finally {
            if (request === this.request) this.state.loading = false;
        }
    }
    async changeMonth(ev) {
        if (!/^\d{4}-\d{2}$/.test(ev.target.value)) return;
        this.state.month = ev.target.value;
        this.state.team = '';
        await this.load();
    }
    async changeTeam(ev) { this.state.team = ev.target.value; await this.load(); }
    money(amount) {
        return new Intl.NumberFormat((this.user.lang || 'en-US').replace('_', '-'), { maximumFractionDigits: 2, minimumFractionDigits: 2 }).format(amount || 0);
    }
    get percent() { return this.state.data?.target ? Math.round(this.state.data.net / this.state.data.target * 1000) / 10 : 0; }
    get ringStyle() { return `--progress:${Math.max(0, Math.min(100, this.percent))}%`; }
    get maxDaily() { return Math.max(1, ...(this.state.data?.daily || []).map(d => Math.abs(d.net))); }
    barStyle(day) { return `height:${Math.max(3, Math.abs(day.net) / this.maxDaily * 100)}%`; }
    personStyle(person) {
        const max = Math.max(1, ...(this.state.data?.people || []).map(p => Math.abs(p.amount)));
        return `width:${Math.max(0, Math.min(100, Math.abs(person.amount) / max * 100))}%`;
    }
    openLedger(extra = []) {
        return this.action.doAction({ type: 'ir.actions.act_window', name: _t('Commission ledger'), res_model: 'sales.commission.entry', views: [[false, 'list'], [false, 'form'], [false, 'pivot']], domain: [...this.state.data.domain, ...extra] });
    }
    openReview() { return this.openLedger([['status', '=', 'review']]); }
    openPerson(person) { return this.openLedger([['user_id', '=', person.id]]); }
    openRules() { return this.action.doAction('sales_region_commission.rule_action'); }
    openTargets() { return this.action.doAction('sales_region_commission.target_action'); }
}
registry.category('actions').add('sales_region_commission.dashboard', CommissionDashboard);
