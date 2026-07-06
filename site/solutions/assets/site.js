const $ = (id) => document.getElementById(id);
$('year').textContent = new Date().getFullYear();
async function loadConfig(){
  const cfg = await fetch('/api/form-config').then(r=>r.json()).catch(()=>({services:['AWS / cloud setup'], timelines:['This month'], budgets:['Not sure yet']}));
  const fill = (el, vals) => { el.innerHTML = vals.map(v=>`<option>${v}</option>`).join(''); };
  fill($('serviceSelect'), cfg.services || []);
  fill($('timelineSelect'), cfg.timelines || []);
  fill($('budgetSelect'), cfg.budgets || []);
}
loadConfig();
$('contactForm').addEventListener('submit', async (e)=>{
  e.preventDefault();
  const data = Object.fromEntries(new FormData(e.target).entries());
  $('contactStatus').textContent = 'Sending...';
  const res = await fetch('/api/contact', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(data)});
  const json = await res.json().catch(()=>({ok:false,error:'Unexpected response'}));
  $('contactStatus').textContent = json.ok ? 'Thanks — your request was saved.' : (json.error || 'Something went wrong.');
  if(json.ok) e.target.reset();
});
$('chatForm').addEventListener('submit', async (e)=>{
  e.preventDefault();
  const data = Object.fromEntries(new FormData(e.target).entries());
  $('chatStatus').textContent = 'Opening conversation...';
  const res = await fetch('/api/chat/start', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(data)});
  const json = await res.json().catch(()=>({ok:false,error:'Unexpected response'}));
  if(json.ok){ window.location.href = json.url; }
  else { $('chatStatus').textContent = json.error || 'Something went wrong.'; }
});
