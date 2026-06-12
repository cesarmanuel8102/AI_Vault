async function refresh(){const r=await fetch('/brain-dashboard/status');document.getElementById('status').textContent=JSON.stringify(await r.json(),null,2)}
async function post(url){await fetch(url,{method:'POST'}); await refresh()}
async function chat(){const message=document.getElementById('msg').value; const r=await fetch('/brain-dashboard/chat',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({message})}); document.getElementById('chat').textContent=JSON.stringify(await r.json(),null,2)}
refresh(); setInterval(refresh,10000);
