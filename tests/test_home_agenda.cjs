const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const context = {window: {}, document: {getElementById: () => null}, Intl, Date};
vm.createContext(context);
vm.runInContext(fs.readFileSync('app/static/home-agenda.js', 'utf8'), context);
const {daily, route, today} = context.window.WallboardHomeAgenda;
const people = [{id:'family',name:'Familjen',color:'#ffa080'},{id:'a',name:'Anna',aliases:['Annie']},{id:'e',name:'Erik'}];
const data = {people, preferences:{calendarMode:'mixed'}, events:[
 {id:'yesterday',date:'2026-10-29',title:'Yesterday'},
 {id:'past',date:'2026-10-30',time:'08:00',end:'09:00',title:'Past'},
 {id:'next',date:'2026-10-30',time:'16:30',end:'18:00',title:'Next',people:['a']},
 {id:'ongoing',date:'2026-10-30',time:'10:00',end:'12:00',title:'Ongoing'},
 {id:'trip',date:'2026-10-29',endDate:'2026-10-31',title:'Trip'},
 {id:'tomorrow',date:'2026-10-31',title:'Tomorrow'}]};
const record = {id:'r',date:'2026-10-30',summary:'Annie, Erik – Practice',time:'17:00',end:'18:00',writable:true};
const day = '2026-10-30', now = new Date('2026-10-30T10:00:00Z');
test('uses the Stockholm date at midnight and across summer time',()=>{
 assert.equal(today(new Date('2026-10-29T23:15:00Z')),day);
 assert.equal(today(new Date('2026-06-30T22:15:00Z')),'2026-07-01');
});
test('routes online names and aliases identically to Family Planner',()=>{
 const e=route(record,data);
 assert.equal(e.title,'Practice'); assert.equal(e.people.join(','),'a,e');
 assert.equal(e.onlineRecord,record);assert.equal(e.id,'icloud-r');
 assert.equal(route({...record,summary:'Unknown – Original title'},data).title,'Unknown – Original title');
 assert.equal(route({...record,summary:'Unknown'},data).people[0],'family');
 assert.equal(route({...record,stale:true},data).writable,false);
});
test('includes multi-day and all-day entries, orders upcoming before finished, and excludes other days',()=>{
 const rows=daily(data,[record],day,now), ids=rows.map(e=>e.id);
 assert.equal(rows.length,5);assert.equal(ids[0],'trip');assert.equal(ids[1],'ongoing');
 assert.equal(ids.at(-1),'past');assert.ok(ids.includes('icloud-r'));
});
test('respects local, online-only (icloud) and mixed modes without duplicate shared rows',()=>{
 assert.equal(daily({...data,preferences:{calendarMode:'local'}},[record],day,now).length,4);
 assert.equal(daily({...data,preferences:{calendarMode:'icloud'}},[record],day,now).length,1);
 assert.equal(daily(data,[record],day,now).filter(e=>e.id==='icloud-r').length,1);
});
