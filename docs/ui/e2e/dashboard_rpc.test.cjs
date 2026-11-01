const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');
function dashboard(name, file) {
    const source = fs.readFileSync(path.join(__dirname, '../../../addons', file), 'utf8')
        .replace(/^import .*;\s*$/mg, '').replace(`export class ${name}`, `class ${name}`)
        .replace(/^registry\.category.*$/mg, '') + `\nglobalThis.Dashboard=${name};`;
    const ctx = {Component:class{}, Intl, _t:s=>s};
    vm.createContext(ctx); vm.runInContext(source,ctx);
    const d = Object.create(ctx.Dashboard.prototype);
    d.requestVersion=0;
    d.state={loading:false,error:null,data:{stale:true},vehicleId:1,fmcgCategory:'',areaIds:[],salesmanIds:[],channelIds:[],periodKey:null};
    const pending=[];
    d.orm={call:(_model,_method,_args,filters)=>new Promise((resolve,reject)=>pending.push({resolve,reject,filters}))};
    return {d,pending};
}
for (const [name,file] of [
    ['WmsDashboard','id_dashboard_wms/static/src/js/wms_dashboard.js'],
    ['MonetaryDashboard','id_dashboard_monetary/static/src/js/monetary_dashboard.js'],
    ['SalesProductivity','id_dashboard_sales/static/src/js/sales_productivity.js'],
]) {
    test(`${name}: late success cannot replace a newer filter result`,async()=>{
        const {d,pending}=dashboard(name,file);
        const a=d.load(); d.state.vehicleId=2; const b=d.load();
        pending[1].resolve({selected:2}); await b;
        pending[0].resolve({selected:1}); await a;
        assert.equal(d.state.data.selected,2); assert.equal(d.state.loading,false);
    });
    test(`${name}: latest error clears stale values`,async()=>{
        const {d,pending}=dashboard(name,file);const a=d.load();
        pending[0].reject(new Error('latest error'));await a;
        assert.equal(d.state.data,null);assert.equal(d.state.error,'latest error');assert.equal(d.state.loading,false);
    });
    test(`${name}: late error cannot hide the newer filter result`,async()=>{
        const {d,pending}=dashboard(name,file);
        const a=d.load(),b=d.load();pending[1].resolve({selected:2});await b;
        pending[0].reject(new Error('old error'));await a;
        assert.equal(d.state.data.selected,2);assert.equal(d.state.error,null);
    });
}
test('monetary drill-down preserves invoice scope and customer company',()=>{
    const {d}=dashboard('MonetaryDashboard','id_dashboard_monetary/static/src/js/monetary_dashboard.js');
    const scope=[['company_id','in',[1]],['area_id','in',[4]],['salesman_id','in',[9]]];
    d.state.data={domains:{aging:scope}};
    let action; d.action={doAction:a=>{action=a;}};
    d.openCustomerInvoices(12,'Outlet',1);
    assert.deepEqual(Array.from(action.domain,x=>Array.from(x)),[...scope,['partner_id','=',12],['company_id','=',1]]);
    action=null;d.state.loading=true;d.openAllInvoices();assert.equal(action,null);
});
