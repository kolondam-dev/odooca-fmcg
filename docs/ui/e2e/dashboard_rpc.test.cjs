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

test('Sales money uses normalized company currency and preserves decimal precision',()=>{
    const {d}=dashboard('SalesProductivity','id_dashboard_sales/static/src/js/sales_productivity.js');
    d.state.data={currency:'USD',currency_digits:2};
    assert.equal(d.money(12.5),'USD 12,50');
    d.state.data={currency:'IDR',currency_digits:0};assert.equal(d.money(12500),'Rp 12.500');
});

test('historical ledger drilldown uses server snapshot scope and blocks stale clicks',()=>{
    const {d}=dashboard('MonetaryDashboard','id_dashboard_monetary/static/src/js/monetary_dashboard.js');
    const domain=[['date','<=','2025-01-31'],['company_id','in',[1]]];
    d.state.data={ar_history:{available:true,domain}};
    let action;d.action={doAction:a=>{action=a;}};
    d.openHistoricalLedger();assert.equal(action.domain,domain);
    action=null;d.state.loading=true;d.openHistoricalLedger();assert.equal(action,null);
});
test('cohort and margin source drilldowns preserve exact server record ids',()=>{
    const {d}=dashboard('WmsDashboard','id_dashboard_wms/static/src/js/wms_dashboard.js');
    d.state.data={cohort:{source_ids:[2,3]}};let action;d.action={doAction:a=>{action=a;}};
    d.openCohort();assert.equal(JSON.stringify(action.domain),'[["id","in",[2,3]]]');
    const {d:s}=dashboard('SalesProductivity','id_dashboard_sales/static/src/js/sales_productivity.js');
    s.action=d.action;s.openMarginSources({available:true,invoice_ids:[4],journal_ids:[5]});
    assert.equal(JSON.stringify(action.domain),'[["id","in",[4,5]]]');
    action=null;s.openMarginSources({available:false});assert.equal(action,null);
});
test('historical AR amounts preserve company-currency precision',()=>{
    const {d}=dashboard('MonetaryDashboard','id_dashboard_monetary/static/src/js/monetary_dashboard.js');
    d.state.data={currency:'USD',currency_digits:2};assert.equal(d.money(12.34),'USD 12,34');
    d.state.data={currency:'IDR',currency_digits:0};assert.equal(d.money(12),'Rp 12');
});
test('asset units preserve small volumes and fractional currency',()=>{
    const {d}=dashboard('WmsDashboard','id_dashboard_wms/static/src/js/wms_dashboard.js');
    d.state.data={currency:'USD',currency_digits:2};
    assert.equal(d.physical(.0123),'0,0123');assert.equal(d.physical(.00001),'<0,0001');
    assert.equal(d.assetMoney(.6),'USD 0,60');assert.equal(d.physical(null),'—');
});
test('asset source drilldowns preserve scope and block stale clicks',()=>{
    const {d}=dashboard('WmsDashboard','id_dashboard_wms/static/src/js/wms_dashboard.js');
    let a;d.action={doAction:v=>{a=v;}};
    const domain=[['company_id','=',1],['location_id','child_of',3]];
    d.state.data={assets:{trip_domain:domain}};d.openAssetQuants({domain});assert.equal(a.domain,domain);
    d.openAssetTrip();assert.equal(a.domain,domain);
    a=null;d.state.loading=true;d.openAssetTrip(3);assert.equal(a,null);
});
test('late AR evidence capture does not navigate after filter change',async()=>{
    const {d,pending}=dashboard('MonetaryDashboard','id_dashboard_monetary/static/src/js/monetary_dashboard.js');
    d.state.data={ar_history:{available:true,as_of:'2026-07-31',comparison:'2026-07-01'}};
    let action=null;d.action={doAction:a=>{action=a;}};
    const save=d.captureArEvidence();d.requestVersion++;pending[0].resolve(7);await save;
    assert.equal(action,null);assert.equal(d.capturePending,false);
});
test('AR evidence capture preserves explicit dates and successful source action',async()=>{
    const {d,pending}=dashboard('MonetaryDashboard','id_dashboard_monetary/static/src/js/monetary_dashboard.js');
    d.state.data={ar_history:{available:true,as_of:'2026-07-31',comparison:'2026-07-01'}};
    let action;d.action={doAction:a=>{action=a;}};
    const save=d.captureArEvidence();assert.equal(pending[0].filters.as_of,'2026-07-31');
    pending[0].resolve(7);await save;assert.equal(action.res_id,7);
});
