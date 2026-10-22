/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { FormController } from "@web/views/form/form_controller";
import { bus } from "./ziwo_service";

let _triggered = false;

patch(FormController.prototype, {
    setup() {
        super.setup();
        const currentModel = this.modelParams.config.resModel;
        if (currentModel && currentModel === 'agent.screen' && !_triggered) {
            _triggered = true;
            bus.trigger('forge_ziwo_onAgentScreen');
            setTimeout(() => { _triggered = false; }, 1000);
        }
    },
});