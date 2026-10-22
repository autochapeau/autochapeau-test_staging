/** @odoo-module **/

import { Component } from "@odoo/owl";

export class ZiwoSystrayItem extends Component {
    setup() {
        super.setup();
        this.isDarkMode = this._isDarkMode();
    }
    _isDarkMode() {
        const links = Array.from(document.getElementsByTagName('link'));
        const scripts = Array.from(document.getElementsByTagName('script'));
        const assetsWebDarkCSS = links.some(link => link.href.includes('web.assets_web_dark.min.css'));
        const assetsWebDarkJS = scripts.some(script => script.src.includes('web.assets_web_dark.min.js'));
        return assetsWebDarkCSS && assetsWebDarkJS;
    }
    onClick() {
        this.props.bus.trigger('forge_ziwo_onToggleDisplay');
    }
}
ZiwoSystrayItem.template = "forge_ziwo.ZiwoSystrayItem";
