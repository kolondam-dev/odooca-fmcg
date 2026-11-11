const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');
const root=path.join(__dirname,'../../..');
function action(isSales = true) {
    let source=fs.readFileSync(path.join(root,'addons/id_dashboard_redesign/static/src/action.js'),'utf8');
    source=source.replace(/^import .*;\s*$/mg,'').replace('export class RedesignAction','class RedesignAction')
        +'\nglobalThis.Action=RedesignAction;';
    const actions = new Map();
    const ctx={registry:{category:()=>({add:(key, value)=>actions.set(key, value)})}, user:{hasGroup:async()=>isSales},
        Domain:{and:domains=>({toList:()=>domains.flat()})}, Dialog:class{}, Component:class{}, DashboardShell:class{}, ApprovedControls:class{}, Intl, _t:s=>s, adaptSource:(_id,response)=>({source:response.source})};
    vm.createContext(ctx);vm.runInContext(source,ctx);
    const d=Object.create(ctx.Action.prototype);
    d.generation=0; d.state={loading:false,error:null,data:{old:true},filters:{dimensions:{}},scope:{company_names:[]}};
    const pending=[];
    d.orm={call:(_model,_method,_args,params)=>new Promise((resolve,reject)=>pending.push({resolve,reject,params}))};
    return {d,pending,actions};
}
const query=(day='01')=>({period:{from:`2026-10-${day}`,to:'2026-10-31'},filters:{sku:{mode:'out',ids:['9']}}});
test('D1 late responses cannot replace the current data/query',async()=>{
    const {d,pending}=action();
    const a=d.load(query()), b=d.load(query('02'));
    pending[1].resolve({source:{selected:2}});assert.equal(await b,true);
    pending[0].resolve({source:{selected:1}});assert.equal(await a,false);
    assert.equal(d.state.data.source.selected,2);
    assert.equal(d.query.period.from,'2026-10-02');
    assert.equal(pending[1].params.params.query.filters.sku.ids[0],9);
    assert.equal(pending[1].params.params.query.filters.sku.mode,'out');
});
test('D1 source failure retains the applied scope/data and reports failure',async()=>{
    const {d,pending}=action(); d.query=query();
    const old=d.state.data, result=d.load(query('02'));
    pending[0].reject(new Error('Source denied'));
    assert.equal(await result,false);assert.equal(d.state.data,old);
    assert.equal(d.query.period.from,'2026-10-01');
    assert.equal(d.state.loading,false);assert.equal(d.state.error,'Source denied');
});
test('D1 map drill offers both exact lines and containing native orders',async()=>{
    const {d}=action(), calls=[];
    let choice;
    d.dialog={add:(_component, props)=>{choice=props.open;}};
    d.action={loadAction:async id=>{
        assert.equal(id,'sale.action_orders');
        return {res_model:'sale.order',domain:[['state','=','sale']]};
    },doAction:v=>calls.push(v)};
    const domain=[['company_id','in',[8]],['product_id','in',[9]]];
    d.state.data={cityDrills:{'71.71':{model:'sale.order.line',domain}}};
    await d.openDocument({dimension:'city_code',code:'71.71'});
    await choice(true);
    assert.equal(calls[0].res_model,'sale.order.line');
    assert.equal(calls[0].domain,domain);
    await choice(false);
    assert.equal(calls[1].res_model,'sale.order');
    assert.equal(calls[1].domain[1][0],'order_line');
    assert.equal(calls[1].domain[1][1],'any');
    assert.equal(calls[1].domain[1][2],domain);
    d.generation++;
    await choice(true);
    assert.equal(calls.length,2);
});
test('Dashboards entry dispatches by Sales group',async()=>{
    assert.equal(await action().actions.get('id_dashboard_redesign.default')(),
        'id_dashboard_sales.action_sales_productivity');
    assert.equal(await action(false).actions.get('id_dashboard_redesign.default')(),
        'spreadsheet_dashboard.ir_actions_dashboard_action');
});
test('D1 adapter uses company currency, signed values, real comparison and no fixture fallback',()=>{
    let source=fs.readFileSync(path.join(root,'addons/id_dashboard_redesign/static/src/adapters.js'),'utf8');
    source=source.replace(/^import .*;\s*$/mg,'').replace('export function adaptSource','function adaptSource')+'\nglobalThis.adapt=adaptSource;';
    const ctx={Intl,_t:s=>s};vm.createContext(ctx);vm.runInContext(source,ctx);
    const raw={total:{net:-50,gross:-60,discount:-10,orders:1,aov:-50,pjp:{}},
        period:{start:'2026-10-01',end:'2026-10-01'},currency:'USD',line_domain:[['id','in',[99]]],
        trend:[{date:'2026-10-01',net:-50}],principal:[],channel:[],city:[],
        monthly:[{month:'2026-10',net:-900000,discount_ratio:0}],
        salesmen:[{name:'Unavailable target',net:-50,orders:1,outlets:1,pjp:{}}]};
    const result=ctx.adapt('D1',{source:raw,read_at:'now'},{});
    assert.equal(result.kpis[2].cur,'USD');assert.equal(result.kpis[2].num,'-50');
    assert.equal(result.kpis[1].num,'—');assert.equal(result.kpis[3].num,'—');
    assert.equal(result.config.panel6.min,-0.00005);assert.equal(result.__available['D1.7'],false);
    assert.equal(result.kpis[2].drill.domain[0][2][0],99);
    assert.equal(result.trows[0][4],'—');
    assert.equal(result.mBars[0].t,'-0,0009');
});
test('D1 controls defer translations until mounted after webclient startup',()=>{
    let source=fs.readFileSync(path.join(root,'addons/id_dashboard_ui/static/src/core/controls_controller.js'),'utf8');
    source=source.replace(/^import .*;\s*$/mg,'').replace('export function mountDashboardControls','function mountDashboardControls');
    const ctx={_t:()=>{throw new Error('translations have not been loaded');}};
    vm.createContext(ctx);assert.doesNotThrow(()=>vm.runInContext(source,ctx));
});

test('D1 initial source failure retains controls for a narrower retry',async()=>{
    const {d,pending}=action();d.initialQuery=query();
    const first=d.load(d.initialQuery);pending[0].reject(new Error('Narrow the period'));
    assert.equal(await first,false);
    const options=d.recoveryOptions;
    assert.equal(options.initialQuery.period.from,'2026-10-01');
    assert.equal(options.dimensions.length,0);
    const template=fs.readFileSync(path.join(root,'addons/id_dashboard_redesign/static/src/action.xml'),'utf8');
    assert.match(template,/<ApprovedControls t-if="!state.data and state.filters.dimensions"/);
});
