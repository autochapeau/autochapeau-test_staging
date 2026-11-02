/** @odoo-module **/
import { Component, useState } from '@odoo/owl';
import { Dialog } from '@web/core/dialog/dialog';
import { registry } from '@web/core/registry';
import { useService } from '@web/core/utils/hooks';
import { commissionMenus, menuIcon } from '../navigation';
import { GUIDE_TOPICS } from './guide_data';
import { GUIDE_DETAILS } from './guide_details';

class GuideScreenshot extends Component {
    static template = 'sales_region_commission.GuideScreenshot';
    static components = { Dialog };
    static props = { title: String, src: String, close: Function };
}

export class CommissionGuide extends Component {
    static template = 'sales_region_commission.Guide';
    setup() {
        this.menu = useService('menu');
        this.dialog = useService('dialog');
        this.state = useState({ lang: 'ar', topic: 'overview' });
    }
    get menus() { return commissionMenus(this.menu); }
    get topics() { return GUIDE_TOPICS; }
    get topic() { return this.topics.find(t => t.id === this.state.topic) || this.topics[0]; }
    get detail() { return GUIDE_DETAILS[this.topic.id]; }
    canOpen(topic) { return this.menus.some(m => m.xmlid === 'sales_region_commission.' + topic.menu); }
    get currentIndex() { return this.topics.indexOf(this.topic); }
    text(ar, en) { return this.state.lang === 'ar' ? ar : en; }
    tr(pair) { return Array.isArray(pair) ? pair[this.state.lang === 'ar' ? 0 : 1] : pair; }
    number(value) { return String(value).padStart(2, '0'); }
    icon(topic) { return menuIcon({xmlid: topic.menu}); }
    image(topic) { return '/sales_region_commission/static/src/guide/screens/' + topic.image + '?v=17.0.4.0.0'; }
    select(topic) { this.state.topic = topic.id; }
    enlarge() { this.dialog.add(GuideScreenshot, { title: this.tr(this.topic.title), src: this.image(this.topic) }); }
    next() { this.select(this.topics[(this.currentIndex + 1) % this.topics.length]); }
    async open() {
        const item = this.menus.find(m => m.xmlid === 'sales_region_commission.' + this.topic.menu);
        if (item) await this.menu.selectMenu(item);
    }
}
registry.category('actions').add('sales_region_commission.guide', CommissionGuide);
