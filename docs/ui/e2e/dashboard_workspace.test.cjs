const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');
function shell(collapsed=false) {
    const writes=[];
    const source=fs.readFileSync(path.join(__dirname,'../../../addons/id_ui_shell/static/src/shell/id_shell_service.js'),'utf8')
        .replace(/^import .*;\s*$/mg,'').replace('export const idShellService','const idShellService')
        .replace(/^registry\.category.*$/mg,'')+'\nglobalThis.service=idShellService;';
    const context={reactive:s=>s,user:{settings:{id_ui_shell:'sidebar'}},browser:{localStorage:{
        getItem:()=>collapsed?'1':'0',setItem:(...args)=>writes.push(args)}}};
    vm.createContext(context);vm.runInContext(source,context);
    return {api:context.service.start(),writes};
}
test('dashboard panel toggles are temporary and preserve the user preference',()=>{
    for(const preference of [false,true]) {
        const {api,writes}=shell(preference);
        const release=api.enterDashboard();
        assert.equal(api.state.dashboardPanelExpanded,false);
        api.togglePanel();assert.equal(api.state.dashboardPanelExpanded,true);
        assert.equal(api.state.panelCollapsed,preference);
        assert.equal(writes.length,0);
        release();release();assert.equal(api.state.dashboardCount,0);
        api.togglePanel();assert.equal(api.state.panelCollapsed,!preference);
        assert.equal(writes.length,1);
    }
});
test('overlapping dashboard actions release only their own workspace lease',()=>{
    const {api}=shell();const a=api.enterDashboard();api.togglePanel();const b=api.enterDashboard();
    a();assert.equal(api.state.dashboardCount,1);assert.equal(api.state.dashboardPanelExpanded,true);
    b();assert.equal(api.state.dashboardCount,0);
    const c=api.enterDashboard();assert.equal(api.state.dashboardPanelExpanded,false);c();
});
