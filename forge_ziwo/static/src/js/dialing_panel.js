/** @odoo-module **/

// import Widget from "@web/legacy/js/core/widget";
import { _t } from "@web/core/l10n/translation";
import { Component, onMounted, onWillUnmount, useState } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";
import { jsonrpc } from "@web/core/network/rpc_service";

export class DialingPanel extends Component {
    static template = 'forge_ziwo.ZiwoDialingPanel';

    setup() {
        super.setup();
        this.win = false;
        this.title = this._getTitle();
        this.callRecord = false;
        this.model = false;
        this.record = false;
        this.record_status = false;
        this.session = false;
        this.bus = this.props.bus;
        this.busService = this.env.services.bus_service;
        this.action = useService("action");
        this.el = DialingPanel.template;
        this.$el = $(this.el);

        this.state = useState({
            isVisible: false,
            isFolded: false,
        });

        onMounted(() => {
            this._start();
        });

        onWillUnmount(() => {
            this._destroy();
        });

//        this.busService.addEventListener('ziwo/bus', this._onBusNotification.bind(this));
//        this.busService.addEventListener('notification', this._onBusNotification.bind(this));
//        this.busService.subscribe('ziwo/bus', (payload) => this._onZiwoBusNotification(payload));
    }

    async call_rpc(data_input) {
        return jsonrpc("/web/dataset/call_kw/" + data_input.model + "/" + data_input.method, {
            model: data_input.model,
            method: data_input.method,
            args: data_input.args,
            kwargs: {},
        })
    }

    async _start() {
        this.bus.addEventListener('forge_ziwo_onToggleDisplay', this._showPanel.bind(this));
        this.bus.addEventListener('forge_ziwo_onAgentScreen', this._agentScreenDetected.bind(this));
        this.busService.addEventListener('notification', this._onBusNotification.bind(this));
//        this.busService.addEventListener('ziwo/bus', this._onBusNotification.bind(this));
        $(document).ready(() => {
            $('#ziwoFrame').on('load', () => {
                this._updateWindow()
            });
        });

    }

    _destroy() {
        if (this.win !== false) {
            this.bus.removeEventListener('forge_ziwo_onToggleDisplay', this._showPanel.bind(this));
            this.bus.removeEventListener('forge_ziwo_onAgentScreen', this._agentScreenDetected.bind(this));
            this.busService.removeEventListener('notification', this._onBusNotification.bind(this));
//            this.busService.removeEventListener('ziwo/bus', this._onBusNotification.bind(this));
//            this.busService.unsubscribe('ziwo/bus', this._onBusNotification.bind(this));
            if (this.win !== false) {
                this.win.removeEventListener('ziwo-call-all', this._onZiwoEvent);
                this.win.removeEventListener('ziwo-call-active', this._onZiwoEvent);
            }
        };
    }

    _updateWindow() {
        if (this.win === false && document.getElementById('ziwoFrame') !== null) {
            this.win = document.getElementById('ziwoFrame').contentWindow;
            this.win.addEventListener('ziwo-call-all', this._onZiwoEvent.bind(this));
            this.win.addEventListener('ziwo-call-active', this._onZiwoEvent.bind(this));
        }
        if (!this.session) {
            this.session = JSON.parse(localStorage.getItem('ZIWO_SESSION_DETAILS'));
        }
    }

    _getTitle() {
        return _t("Ziwo");
    }

    async _showPanel() {
        if (!this.state.isVisible) {
            this.state.isVisible = true;
            if (this.state.isFolded) {
                await this._toggleFold();
            }
        } else {
            await this._toggleFold();
        }
        
    }

    async _showPanelOnCall() {
        if (!this.state.isVisible) {
            this.state.isVisible = true;
            if (this.state.isFolded) {
                await this._toggleFold();
            }
        }
        if (this.state.isFolded) {
            await this._toggleFold();
        }
    }

    async _hidePanel() {
        if (this.state.isVisible) {
            this.state.isVisible = false;
        }
    }

    async _toggleFold() {
        this.state.isFolded = !this.state.isFolded;
    }

//    async _onZiwoBusNotification(payload) {
//        console.log('ZIWO BUS PAYLOAD: ', payload);
//        switch(payload.action) {
//            case 'call':
//                this._showPanelOnCall();
//                this.model = payload.model;
//                this.record = payload.record;
//                this.win.ZIWO.calls.startCall(payload.mobile)
//                    .catch((error) => {
//                        console.error('Error while starting call:', error);
//                    });
//                break;
//            case 'update':
//                this.model = payload.model;
//                this.record = payload.record;
//                this._updateCallModel()
//                    .catch((error) => {
//                        console.error('Error while updating model:', error);
//                    });
//                break;
//            case 'get':
//                this._updateCallRecording(payload.record)
//                    .catch((error) => {
//                        console.error('Error while updating call recording:', error);
//                    });
//                break;
//        }
//    }

    async _onBusNotification({ detail: notifications }) {
        await this._updateWindow()
        for (const {payload, type} of notifications) {
            if (type === 'ziwo/bus') {
                if (payload.action === 'call') {
                    this._showPanelOnCall();
                    this.model = payload.model;
                    this.record = payload.record;
                    this.win.ZIWO.calls.startCall(payload.mobile)
                        .catch((error) => {
                            console.error('Error while starting call:', error);
                        });
                }
                if (payload.action === 'update') {
                    this.model = payload.model;
                    this.record = payload.record;
                    this._updateCallModel()
                        .catch((error) => {
                            console.error('Error while updating model:', error);
                        });
                }
                if (payload.action === 'get') {
                    this._updateCallRecording(payload.record)
                        .catch((error) => {
                            console.error('Error while updating call recording:', error);
                        });
                }
            }
            
        }
    }

    async _onZiwoEvent({ detail: event }) {
        await this._updateWindow();
        const isInternal = event.call && event.call.participants[0].isInternal;
        if (!isInternal) {
            switch (event.type) {
                case 'ringing':
                case 'early':
                    var mobile = event.call.participants[0].number;
                    var call_type = event.call.direction;
                    var call_id = event.call.callId;
                    var call_time = event.call.startedAt;
                    var is_transfer = event.call.isTransfer;
                    var verto_call_id = event.call.vertoPrimaryCallId;

                    await this._showPanelOnCall();

                    if (!is_transfer && verto_call_id){
                        if (call_type === 'inbound') {
                            await this._createCallRecord(mobile, call_type, verto_call_id, call_time);
                        } else {
                            await this._transferCallRecord(verto_call_id,'blind');
                        }
                    
                    } else if (is_transfer) {
                        var parentCallId = event.call.userVariables.verto_h_transfer_origin_call_id;
                        await this._transferCallRecord(parentCallId,'attend');
                    
                    }  else if (this.callRecord === false){
                        await this._createCallRecord(mobile, call_type, call_id, call_time);

                    } else {
                        await this._updateCallID(call_id, call_time);

                    }
                    break;
                case 'answering':
                    this.record_status = 'answered';
                    await this._updateCallStatus(this.record_status);
                    break;
                case 'hangup':
                    var call_states = event.call.states;
                    var call_type = event.call.direction;
                    var cause = event.cause;
                    if (!this.record_status && !call_states.find(s => s.state === 3)) {
                        if (call_type === "outbound"){
                            if (!cause || cause === "NORMAL_CLEARING" || cause === "NO_USER_RESPONSE") {
                                this.record_status = 'rejected';
                            } else {
                                this.record_status = 'missed';
                            }
                        } else {
                            this.record_status = 'missed';
                        }
                        await this._updateCallStatus(this.record_status);
                    }
                    break;
                case 'destroy':
                    await this._endCallProcedure();
                    break;
            }
        } else {
            await this._showPanelOnCall();
        }
    }

    async _endCallProcedure() {
        await this._updateWindow();
        await this._updateCallModel(!this.model);
        await this._createCallRecording();
        await this._createCallMessage();
        await this._clearData();
    }

    async _clearData() {
        this.callRecord = false;
        this.model = false;
        this.record = false;
        this.record_status = false;
    }

    async _createCallRecord(mobile, call_type, call_id, call_time) {
        const c2c_override = await this.call_rpc({
            model: 'forge.sudo.override',
            method: 'get_param_navigate_outbound_calls_c2c',
            args: [],
        });

        await this.call_rpc({
            model: 'ziwo.history',
            method: 'create_call_record',
            args: [mobile,call_type,call_id,call_time, this.model, this.record],
        }).then((result) => {
            this.callRecord = result.record_id;
            const override = this.model && c2c_override;
            if (result.action && !override) {
                this._performWindowAction(result.action)
            }
        });
    }

    async _transferCallRecord(parent_call_id, transfer_type) {
        await this.call_rpc({
            model: 'ziwo.history',
            method: 'transfer_call_record',
            args: [parent_call_id, transfer_type],
        }).then((result) => {
            this.callRecord = result.record_id;
        });
    }

    async _updateCallRecording(record_id) {
        await this._updateWindow();
        if (!this.session) {
            this.session = JSON.parse(localStorage.getItem('ZIWO_SESSION_DETAILS'));
        }
        await this.call_rpc({
            model: 'ziwo.history',
            method: 'create_call_recording',
            args: [record_id,this.session],
        }).then((result) => {
            if (result.action) {
                this._performClientAction(result.action);
            }
        });
    }

    async _createCallRecording() {
        await this.call_rpc({
            model: 'ziwo.history',
            method: 'create_call_recording',
            args: [this.callRecord,this.session],
        });
    }

    async _updateCallID(call_id, call_time) {
        await this.call_rpc({
            model: 'ziwo.history',
            method: 'update_call_id',
            args: [this.callRecord, call_id, call_time],
        });
    }

    async _updateCallStatus(call_status) {
        await this.call_rpc({
            model: 'ziwo.history',
            method: 'update_call_status',
            args: [this.callRecord,call_status],
        });
    }

    async _createCallMessage() {
        await this.call_rpc({
            model: 'ziwo.history',
            method: 'create_call_message',
            args: [this.callRecord],
        });
    }

    async _updateCallModel(context=false) {
        const args = [this.callRecord, this.model, this.record];
        if (context) {
            const model_regex = /#id=(\d+).*model=([a-z\.]+)/;
            const model_data = this.$el.prevObject[0].baseURI.match(model_regex);
            args.push(context);
            if (model_data){
                args.push(model_data[2]);
                args.push(model_data[1]);
            }
        }
        await this.call_rpc({
            model: 'ziwo.history',
            method: 'update_call_model',
            args: args,
        }).then((result) => {
            if (result.action) {
                this._performWindowAction(result.action);
            }
        });
    }

    async _performWindowAction(result_action) {
        const action = await this.call_rpc({
            model: 'forge.sudo.override',
            method: 'create_act_window',
            args: [result_action],
        });
        this.action.doAction(action);
    }

    async _performClientAction(result_action) {
        const action = await this.call_rpc({
            model: 'forge.sudo.override',
            method: 'create_client_notification',
            args: [result_action],
        });
        this.action.doAction(action);
    }

    async _onToggleDisplay() {
        await this._toggleDisplay();
    }

    async _agentScreenDetected() {
        var model_regex = /model=([a-z\.]+)/;
        var model_data = window.location.href.match(model_regex);
        var model_agent_screen = false;
        if (model_data){
            model_agent_screen = model_data[1];
        }
        if (this.callRecord && (model_agent_screen !== 'agent.screen')){
            var result = await this.call_rpc({
                model: 'ziwo.history',
                method: 'set_agent_screen',
                args: [this.callRecord],
            });
            this._performWindowAction(result);
        }
    }
}
