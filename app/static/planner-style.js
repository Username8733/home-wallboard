"use strict";
// Scoped to the wallboard iframe. Shared calendar settings and source stay intact.
window.WallboardPlannerStyle = String.raw`
html:root,html:root body{background:transparent!important;color:var(--text);font-family:-apple-system,BlinkMacSystemFont,"Inter","Noto Sans",sans-serif;overflow:hidden}
*,*::before,*::after{cursor:none!important}
html:root{--soft:color-mix(in srgb,var(--accent) 10%,transparent);--field:var(--surface);--weekend:color-mix(in srgb,var(--accent) 5%,transparent);--today:color-mix(in srgb,var(--accent) 12%,transparent);--today-heading:color-mix(in srgb,var(--accent) 18%,var(--wb-bg));--today-border:color-mix(in srgb,var(--accent) 30%,transparent);--hover:color-mix(in srgb,var(--accent) 9%,transparent);--week-divider:color-mix(in srgb,var(--muted) 20%,transparent);--weekend-ink:var(--muted);--glass-shadow:#14244016;--sticky:color-mix(in srgb,var(--wb-bg) 86%,white 14%)}
html:root[data-mode="dark"]{--sticky:color-mix(in srgb,var(--wb-bg) 94%,white 6%);--glass-shadow:#00000024}
html:root .app{height:100dvh;min-height:0;max-width:none;margin:0;padding:68px 16px 8px;gap:12px;background:none!important;background-image:none!important;border:0!important;border-radius:0!important;box-shadow:none!important}
html:root .top{display:none!important}
html:root .heading{gap:18px;align-items:center;background:none;border:0;box-shadow:none;flex-shrink:0}
html:root .month-group{gap:14px;min-width:255px;align-items:center;flex-wrap:wrap}
html:root #month-title{font-weight:600;font-size:30px;letter-spacing:-1.3px;white-space:nowrap}
html:root .heading .eyebrow{display:none}
html:root .navigation{gap:5px}
html:root :is(.icon,.today,.view,.add){height:40px;min-height:40px;border-radius:24px}
html:root .today{font-size:12px;padding-inline:13px}
html:root .tools{gap:8px}
html:root .view{padding-inline:13px;font-size:11px}
html:root .add{font-size:12px;padding-inline:15px}
html:root .weather-strip{gap:9px;flex:1;min-width:250px;max-width:460px}
html:root .heading :is(.forecast-card,.outdoor-card){border-radius:24px;background:var(--glass);border:1px solid var(--glass-line);box-shadow:inset 0 1px 0 var(--glass-line),0 6px 20px var(--glass-shadow);min-height:66px;padding:10px 14px}
html:root .weather-kicker{font-size:9px;color:var(--muted)!important}
html:root .outdoor-value{font-size:27px}
html:root .forecast-condition{font-size:14px}
html:root .calendar{flex:1;min-height:0;background:var(--surface);border:1px solid var(--border);border-radius:25px;box-shadow:var(--wb-shadow);backdrop-filter:blur(18px) saturate(130%);-webkit-backdrop-filter:blur(18px) saturate(130%)}
html:root table{background:transparent}
html:root thead th{height:50px;background:var(--sticky);font-weight:600;font-size:14px;border-color:var(--border)}
html:root tbody th{background:var(--sticky)}
html:root .weekend th{background:color-mix(in srgb,var(--accent) 6%,var(--sticky))}
html:root .is-today th{background:var(--today-heading)}
html:root .avatar{width:30px;height:30px;border-radius:50%;font-weight:600}
html:root .date-number{font-size:12px}
html:root .event{border-radius:7px}
html:root[data-mode="dark"] .event{color:color-mix(in srgb,var(--person) 55%,var(--text))}
html:root .footer{font-size:9px;padding:0 6px;min-height:17px}
html:root #fullscreen{display:none}
html:root dialog{background:var(--sticky);border:1px solid var(--glass-line);border-radius:27px;box-shadow:0 24px 90px #0004;color:var(--text)}
html:root input,html:root select,html:root textarea{background:var(--field);color:var(--text);border-color:var(--border);border-radius:13px}
@media(max-width:1000px){html:root .app{padding-top:65px;gap:10px}html:root .heading{flex-wrap:wrap;gap:10px}html:root .month-group{flex:1;min-width:220px}html:root .weather-strip{order:3;flex-basis:100%;max-width:none;min-width:0}html:root .tools{margin-left:auto}html:root .heading :is(.forecast-card,.outdoor-card){min-height:53px;padding:7px 14px}html:root #month-title{font-size:26px}}
@media(max-height:650px){html:root .app{padding-top:60px;padding-bottom:5px;gap:8px}html:root .heading :is(.forecast-card,.outdoor-card){min-height:52px}html:root thead th{height:43px}}
`;
// Weather is already present on Hemma; keep the calendar's toolbar compact.
window.WallboardPlannerStyle += String.raw`
html:root #weather{display:none!important}
html:root .heading{display:flex!important;min-height:42px;flex-wrap:nowrap}
html:root .month-group{display:flex!important;flex-wrap:nowrap;min-width:0;gap:16px;flex:0 1 auto}
html:root .tools{margin-left:auto}
@media(max-width:730px){html:root .heading{flex-wrap:wrap}html:root .month-group{flex-direction:row;align-items:center}html:root .tools{max-width:none}}
`;
window.WallboardPlannerStyle += String.raw`
html:root .wb-keyboard-trigger{border:1px solid var(--glass-line);border-radius:20px;background:var(--glass);color:var(--text);padding:9px 13px;font-size:12px;margin-left:auto;margin-right:10px}
html:root .dialog-head{gap:10px}
html:root .dialog-head h2{min-width:0;flex:1}
`;

// iCloud credentials are managed in the wallboard's general Accounts panel.
window.WallboardPlannerStyle += String.raw`
html:root #icloud-login{display:none!important}
html:root .wb-icloud-account-link{display:block;margin:12px 0;padding:10px 16px;border-radius:14px;border:1px solid var(--border);background:var(--control);color:var(--text)}
`;
