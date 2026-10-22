/** @odoo-module **/

import { ziwoService } from "./ziwo_service";
import { registry } from "@web/core/registry";

registry.category('services').add("forge_ziwo", ziwoService);