/* Grade sob medida — interface.
   Todo o calculo pesado acontece no servidor Python; aqui e so montagem de tela. */

const DIAS = ["Segunda","Terça","Quarta","Quinta","Sexta","Sábado"];
const DIAS3 = ["Seg","Ter","Qua","Qui","Sex","Sáb"];
const DIAS_API = ["Segunda","Terca","Quarta","Quinta","Sexta","Sabado"];
const H0 = 7*60, FATIA = 30, NF = 32;

const $  = s => document.querySelector(s);
const $$ = s => [...document.querySelectorAll(s)];
const el = (t,c,x) => { const e=document.createElement(t); if(c)e.className=c;
                        if(x!==undefined)e.textContent=x; return e; };
const min  = h => { const [a,b]=h.split(":").map(Number); return a*60+b; };
const hhmm = m => String(Math.floor(m/60)).padStart(2,"0")+":"+String(m%60).padStart(2,"0");
const num  = n => (n??0).toLocaleString("pt-BR");

async function api(rota, opcoes){
  const r = await fetch(rota, opcoes);
  const d = await r.json();
  if(d.erro) throw new Error(d.erro);
  return d;
}

const S = { periodo:null, base:null, escolhidas:[], bloqueios:[],
            diasBloq:new Set([0,1,2,3,4]), resultado:null, aba:0,
            cacheDisc:null, carregado:{} };

/* ============================================================ casca */

function trocarPainel(nome){
  $$("#nav button").forEach(b => b.setAttribute("aria-selected", b.dataset.painel===nome));
  $$(".painel").forEach(p => p.classList.toggle("ativo", p.id==="p-"+nome));
  if(nome==="panorama" && !S.carregado.panorama) carregarPanorama();
  if(nome==="vagas"    && !S.carregado.vagas)    carregarVagas();
  if(nome==="dados"    && !S.carregado.dados)    carregarDados();
}
$$("#nav button").forEach(b => b.onclick = () => trocarPainel(b.dataset.painel));

function horasEm(sel, de, ate, val){
  sel.innerHTML="";
  for(let h=de; h<=ate; h++){
    const v = String(h).padStart(2,"0")+":00";
    const o = el("option",null,v); o.value=v; if(v===val) o.selected=true;
    sel.appendChild(o);
  }
}

async function iniciar(){
  const d = await api("/api/base");
  S.base = d;
  const r = d.resumo;
  $("#estado-base").textContent =
    `${num(r.turmas)} turmas · ${num(r.disciplinas_ofertadas)} disciplinas · ${r.arquivo_turmas}`;

  const sel = $("#periodo"); sel.innerHTML="";
  r.periodos.forEach(p => { const o=el("option",null,String(p)); o.value=p; sel.appendChild(o); });
  sel.value = r.periodos[r.periodos.length-1];
  S.periodo = Number(sel.value);
  sel.onchange = () => { S.periodo=Number(sel.value); S.cacheDisc=null; S.carregado={};
                         S.resultado=null; desenharResultado();
                         const ativo=$$("#nav button").find(b=>b.getAttribute("aria-selected")==="true");
                         trocarPainel(ativo.dataset.painel); carregarDepartamentos(); };

  horasEm($("#bq-ini"),7,22,"13:00"); horasEm($("#bq-fim"),8,23,"18:00");
  horasEm($("#f-ini"),7,20,"08:00");  horasEm($("#f-fim"),9,23,"22:00");

  DIAS3.forEach((d,i)=>{
    const b = el("button","dia-btn",d);
    b.setAttribute("aria-pressed", S.diasBloq.has(i));
    b.onclick = () => { S.diasBloq.has(i) ? S.diasBloq.delete(i) : S.diasBloq.add(i);
                        b.setAttribute("aria-pressed", S.diasBloq.has(i)); };
    $("#dias-bloq").appendChild(b);
  });

  [["Faço estágio à tarde", {ini:"08:00",fim:"22:00",seq:2,int:60,dias:4,larga:1},
    [{dias:[0,1,2,3,4],i:"13:00",f:"18:00"}]],
   ["Venho de longe", {ini:"09:00",fim:"19:00",seq:4,int:0,dias:3,larga:1}, []],
   ["Trabalho o dia todo", {ini:"18:00",fim:"23:00",seq:4,int:0,dias:5,larga:1},
    [{dias:[0,1,2,3,4],i:"07:00",f:"18:00"}]],
   ["Duas de manhã e um intervalo", {ini:"09:00",fim:"15:00",seq:2,int:60,dias:4,larga:1},
    [{dias:[0,1,2,3,4],i:"15:00",f:"23:00"}]],
  ].forEach(([nome,f,bl])=>{
    const b = el("button","preset",nome);
    b.onclick = () => {
      $("#f-ini").value=f.ini; $("#f-fim").value=f.fim; $("#f-seq").value=f.seq;
      $("#f-int").value=f.int; $("#f-dias").value=f.dias; $("#f-larga").value=f.larga;
      S.bloqueios = bl.map(x=>({...x, rot:nome.toLowerCase()}));
      render();
    };
    $("#presets").appendChild(b);
  });

  $("#add-bloq").onclick = () => {
    if(!S.diasBloq.size) return;
    const i=$("#bq-ini").value, f=$("#bq-fim").value;
    if(min(f)<=min(i)) return;
    S.bloqueios.push({dias:[...S.diasBloq].sort(), i, f, rot:"indisponível"});
    render();
  };
  $("#montar").onclick = montar;
  $("#cf-rodar").onclick = carregarConflitos;
  ligarBusca();
  carregarDepartamentos();
  render();
}

async function carregarDepartamentos(){
  const d = await api(`/api/disciplinas?periodo=${S.periodo}&limite=99999`);
  S.cacheDisc = d.itens;
  const deptos = [...new Set(d.itens.map(x=>x.departamento).filter(Boolean))].sort();
  for(const id of ["#filtro-depto","#cf-depto"]){
    const sel=$(id); const atual=sel.value;
    sel.innerHTML='<option value="">todos</option>';
    deptos.forEach(x=>{ const o=el("option",null,x); o.value=x; sel.appendChild(o); });
    sel.value=atual;
  }
}

/* ============================================================ montador */

function ligarBusca(){
  const inp=$("#busca"), sug=$("#sugestoes");
  let timer=null;
  inp.oninput = () => {
    clearTimeout(timer);
    timer = setTimeout(async ()=>{
      const q = inp.value.trim();
      sug.innerHTML="";
      if(!q){ sug.classList.remove("aberta"); return; }
      const depto=$("#filtro-depto").value;
      const d = await api(`/api/disciplinas?periodo=${S.periodo}&q=${encodeURIComponent(q)}`
                          + (depto?`&departamento=${encodeURIComponent(depto)}`:""));
      const itens = d.itens.filter(x=>!S.escolhidas.some(e=>e.cod_disciplina===x.cod_disciplina));
      if(!itens.length){ sug.classList.remove("aberta"); return; }
      itens.slice(0,10).forEach(x=>{
        const linha = el("div","sugestao");
        linha.appendChild(el("div",null,x.nome));
        const m = el("div","meta");
        const partes = [x.cod_disciplina, x.creditos+" cr", x.departamento];
        if(x.sem_vaga) partes.push("SEM VAGA");
        else if(x.turma_unica) partes.push("turma única");
        else partes.push(x.turmas_abertas+"/"+x.turmas+" turmas com vaga");
        m.textContent = partes.join(" · ");
        linha.appendChild(m);
        linha.onclick = () => { S.escolhidas.push(x); inp.value="";
                                sug.classList.remove("aberta"); render(); };
        sug.appendChild(linha);
      });
      sug.classList.add("aberta");
    }, 160);
  };
  document.addEventListener("click", e => {
    if(!e.target.closest(".busca")) sug.classList.remove("aberta");
  });
}

function render(){
  const box=$("#escolhidas"); box.innerHTML="";
  if(!S.escolhidas.length) box.appendChild(el("p","vazio","Nenhuma disciplina ainda."));
  let cr=0;
  S.escolhidas.forEach(x=>{
    cr += x.creditos;
    const p = el("div","pilula" + (x.sem_vaga?" travada":(x.turma_unica?" unica":"")));
    p.appendChild(el("div","nome",x.nome));
    p.appendChild(el("span","cr", x.sem_vaga ? "sem vaga"
                    : x.turma_unica ? "turma única" : x.turmas_abertas+" com vaga"));
    const b = el("button",null,"×"); b.setAttribute("aria-label","Remover "+x.nome);
    b.onclick = () => { S.escolhidas = S.escolhidas.filter(y=>y!==x); render(); };
    p.appendChild(b); box.appendChild(p);
  });
  const semVaga = S.escolhidas.filter(x=>x.sem_vaga).length;
  const unicas  = S.escolhidas.filter(x=>x.turma_unica && !x.sem_vaga).length;
  let dica = S.escolhidas.length ? `${cr} créditos pedidos.` : "";
  if(unicas)  dica += ` ${unicas} de turma única — elas viram o esqueleto da grade.`;
  if(semVaga) dica += ` ${semVaga} sem nenhuma vaga: não entram, a menos que você mude a opção abaixo.`;
  $("#dica-escolhidas").textContent = dica;

  const lb=$("#lista-bloq"); lb.innerHTML="";
  S.bloqueios.forEach((b,i)=>{
    const li=document.createElement("li");
    li.appendChild(el("span",null,b.dias.map(d=>DIAS3[d]).join(" ")));
    li.appendChild(el("span","h",b.i+"–"+b.f));
    const x=el("button",null,"×"); x.onclick=()=>{S.bloqueios.splice(i,1); render();};
    li.appendChild(x); lb.appendChild(li);
  });
  $("#montar").disabled = !S.escolhidas.length;
}

async function montar(){
  $("#resultado").innerHTML = '<div class="carregando">montando…</div>';
  const corpo = {
    periodo: S.periodo,
    desejadas: S.escolhidas.map(x=>x.cod_disciplina),
    min_disciplinas: S.escolhidas.length - Number($("#f-larga").value),
    incluir_lotadas: $("#f-lotadas").value==="1",
    bloqueios: S.bloqueios.map(b=>({rotulo:b.rot, dias:b.dias.map(d=>DIAS_API[d]),
                                    hora_inicio:b.i, hora_fim:b.f})),
    formato: {
      inicio_mais_cedo: $("#f-ini").value, fim_mais_tarde: $("#f-fim").value,
      max_aulas_seguidas: Number($("#f-seq").value),
      intervalo_desejado_min: Number($("#f-int").value),
      max_dias_campus: Number($("#f-dias").value),
    },
    quantidade: 4,
  };
  try{
    S.resultado = await api("/api/grades", {
      method:"POST", headers:{"Content-Type":"application/json"}, body:JSON.stringify(corpo)});
    S.aba = 0;
    desenharResultado();
  }catch(e){
    $("#resultado").innerHTML = `<div class="placeholder"><span class="g">Erro ao montar</span>${e.message}</div>`;
  }
}

function desenharResultado(){
  const box = $("#resultado");
  if(!S.resultado){
    box.innerHTML = '<div class="placeholder"><span class="g">Nenhuma grade montada ainda</span>Escolha as disciplinas e clique em montar.</div>';
    return;
  }
  if(!S.resultado.viavel){ desenharDiagnostico(S.resultado); return; }

  box.innerHTML = "";
  const R = S.resultado;

  const abas = el("div","abas-op");
  R.opcoes.forEach((o,i)=>{
    const b = el("button","aba-op");
    b.setAttribute("aria-selected", i===S.aba);
    b.appendChild(el("span","num","opção "+(i+1)));
    b.appendChild(el("span",null,o.rotulo));
    b.onclick = () => { S.aba=i; desenharResultado(); };
    abas.appendChild(b);
  });
  box.appendChild(abas);

  const o = R.opcoes[S.aba];

  const met = el("div","metricas"); met.style.margin="0"; met.style.border="0";
  met.style.borderBottom="1px solid var(--linha)"; met.style.borderRadius="0";
  const m = (rot,val,sub)=>{
    const d=el("div","metrica"); d.appendChild(el("span","rot",rot));
    const v=el("div","val"); v.textContent=val;
    if(sub){ const s=document.createElement("small"); s.textContent=" "+sub; v.appendChild(s); }
    d.appendChild(v); return d;
  };
  met.appendChild(m("dias no campus", o.dias_campus, "de 6"));
  met.appendChild(m("créditos", o.creditos));
  met.appendChild(m("janela total", (o.minutos_lacuna/60).toFixed(1).replace(".",","), "h"));
  met.appendChild(m("menor saldo", o.vagas_minimas, "vagas"));
  box.appendChild(met);

  const pq = el("div","porque");
  pq.innerHTML = `<b>Sobre o formato:</b> ${o.porque.join("; ")}. `
    + `Encontradas <b>${num(R.total_viaveis)}</b> grades viáveis em ${R.ms} ms; `
    + `${R.pareto} não são piores que nenhuma outra.`;
  box.appendChild(pq);

  box.appendChild(desenharSemana(o));
  box.appendChild(desenharTurmas(o));
  box.appendChild(desenharEntrega(o));
}

function desenharSemana(o){
  const wrap = document.createElement("div");
  const env = el("div","grade-envelope");
  const grid = el("div","semana");

  const lc = (min($("#f-ini").value)-H0)/FATIA, lt = (min($("#f-fim").value)-H0)/FATIA;
  const bloq = Array.from({length:6},()=>new Set());
  S.bloqueios.forEach(b => b.dias.forEach(d=>{
    for(let f=(min(b.i)-H0)/FATIA; f<(min(b.f)-H0)/FATIA; f++) bloq[d].add(f);
  }));

  const canto = el("div"); canto.style.gridRow="1/3"; grid.appendChild(canto);
  DIAS3.forEach((d,i)=>{ const c=el("div","cab-dia",d); c.style.gridColumn=i+2; grid.appendChild(c); });

  for(let f=0; f<NF; f++){
    if(f%2===0){
      const mk = el("div","marca-hora",hhmm(H0+f*FATIA));
      mk.style.gridRow=(f+3)+"/span 2"; mk.style.gridColumn="1"; grid.appendChild(mk);
    }
    for(let d=0; d<6; d++){
      const c = el("div","celula"+(f%2===0?" cheia":""));
      if(f<lc||f>=lt) c.classList.add("fora");
      if(bloq[d].has(f)) c.classList.add("bloq");
      c.style.gridRow=f+3; c.style.gridColumn=d+2; grid.appendChild(c);
    }
  }

  o.turmas.forEach(t=>{
    t.blocos.forEach(b=>{
      const a=(min(b.inicio)-H0)/FATIA, z=(min(b.fim)-H0)/FATIA;
      const d = el("div","aula");
      d.style.gridRow=(a+3)+"/span "+Math.max(1,z-a); d.style.gridColumn=b.dia_idx+2;
      d.style.setProperty("--barra", `var(--n${t.nivel})`);
      d.appendChild(el("div","cod",t.turma_id));
      d.appendChild(el("div","nm",t.nome));
      d.title = `${t.nome}\n${t.turma_id} · ${b.dia} ${b.inicio}–${b.fim}`
              + `\n${t.vagas} vagas · ${t.rotulo}` + (b.sala?`\nsala ${b.sala}`:"");
      grid.appendChild(d);
    });
  });

  env.appendChild(grid); wrap.appendChild(env);
  const lg = el("div","legenda");
  lg.innerHTML =
    ['<span><i class="amostra" style="background:var(--n0)"></i>tranquilo</span>',
     '<span><i class="amostra" style="background:var(--n2)"></i>risco médio</span>',
     '<span><i class="amostra" style="background:var(--n4)"></i>risco alto</span>',
     '<span><i class="amostra" style="background:#E4E8EE"></i>fora do horário pedido</span>',
     '<span><i class="amostra hach"></i>você bloqueou</span>'].join("");
  wrap.appendChild(lg);
  return wrap;
}

function desenharTurmas(o){
  const box = el("div","lista-turmas");
  [...o.turmas].sort((a,b)=>a.vagas-b.vagas).forEach(t=>{
    const li = el("div","turma-linha");
    const esq = document.createElement("div");
    esq.appendChild(el("div","id", `${t.turma_id} · ${t.creditos} créditos · ${t.departamento}`));
    esq.appendChild(el("div","nome", t.nome));
    esq.appendChild(el("div","quando", t.horario));
    li.appendChild(esq);
    const dir = el("div","vaga-info");
    const q = el("div","qtd"); q.textContent = t.vagas;
    const s = document.createElement("small"); s.textContent = t.vagas===1?" vaga":" vagas";
    q.appendChild(s); dir.appendChild(q);
    const sel = el("span",`selo n${t.nivel}`, t.rotulo); sel.style.marginTop="4px";
    sel.style.display="inline-block"; dir.appendChild(sel);
    li.appendChild(dir);
    box.appendChild(li);
  });
  return box;
}

function desenharEntrega(o){
  const box = el("div","entrega");
  const acoes = el("div","acoes");

  const b1 = el("button","botao","Copiar códigos");
  b1.onclick = async () => {
    const ids = [...o.turmas].sort((a,b)=>a.vagas-b.vagas).map(t=>t.turma_id);
    try{ await navigator.clipboard.writeText(ids.join(", ")); }catch(e){}
    fetch("/api/planos",{method:"POST",headers:{"Content-Type":"application/json"},
      body:JSON.stringify({periodo:S.periodo, turma_ids:ids})});
    b1.textContent="Copiado"; setTimeout(()=>b1.textContent="Copiar códigos",1800);
  };
  acoes.appendChild(b1);

  const b2 = el("button","botao sec","Copiar plano completo");
  b2.onclick = async () => {
    try{ await navigator.clipboard.writeText(o.texto); }catch(e){}
    b2.textContent="Copiado"; setTimeout(()=>b2.textContent="Copiar plano completo",1800);
  };
  acoes.appendChild(b2);

  const b3 = el("button","botao sec","Sortear outras opções");
  b3.onclick = montar;
  acoes.appendChild(b3);

  box.appendChild(acoes);
  box.appendChild(el("pre","plano", o.texto));

  const rs = el("div","ressalva");
  rs.innerHTML = "<span>As vagas mostradas são as do momento em que o arquivo foi exportado, "
    + "não o saldo de agora. O plano ordena a matrícula da turma com menos vagas para a com mais, "
    + "porque é essa a que você precisa garantir primeiro.</span>";
  box.appendChild(rs);
  return box;
}

function desenharDiagnostico(R){
  const box = $("#resultado"); box.innerHTML="";
  const d = R.diagnostico;
  const w = el("div","diagnostico");

  if(d.tipo==="sem_turma"){
    w.appendChild(el("h3",null,"Não fecha: disciplina sem turma utilizável"));
    const ul = el("ul","saidas");
    d.disciplinas.forEach(x=>{
      const li=document.createElement("li");
      const c=document.createElement("div");
      c.appendChild(el("div",null,x.nome));
      c.appendChild(el("div","mono",x.motivo));
      li.appendChild(c);
      const b=el("button","botao sec","Tirar do plano");
      b.onclick=()=>{ S.escolhidas=S.escolhidas.filter(y=>y.cod_disciplina!==x.cod);
                      render(); montar(); };
      li.appendChild(b); ul.appendChild(li);
    });
    w.appendChild(ul); box.appendChild(w); return;
  }

  w.appendChild(el("h3",null,`Não existe grade com essas ${S.escolhidas.length} disciplinas`));
  const p1 = el("p","dica");
  p1.textContent = "O conflito não é entre todas elas. Estas são as disciplinas em que, tirando qualquer uma, a grade volta a fechar:";
  w.appendChild(p1);

  const nc = el("div","nucleo");
  d.nucleo.forEach(x => nc.appendChild(el("span",null,x.nome)));
  w.appendChild(nc);

  if(d.pares?.length){
    const p2 = el("p","dica");
    p2.innerHTML = d.pares.map(p =>
      `<b>${p.nome_a}</b> e <b>${p.nome_b}</b> não têm nenhuma combinação de turmas sem choque.`
    ).join("<br>");
    w.appendChild(p2);
  }

  if(d.alternativas?.length){
    const p3 = el("p","dica"); p3.style.marginTop="14px";
    p3.innerHTML = "<b>Saídas:</b>"; w.appendChild(p3);
    const ul = el("ul","saidas");
    d.alternativas.forEach(a=>{
      const li = document.createElement("li");
      li.appendChild(el("span",null,"Deixar "+a.nome+" para depois"));
      li.appendChild(el("span","qtd", num(a.grades_liberadas)+" grades · "+a.creditos_restantes+" créditos"));
      const b = el("button","botao sec","Tirar do plano");
      b.onclick = () => { S.escolhidas = S.escolhidas.filter(y=>y.cod_disciplina!==a.remover);
                          render(); montar(); };
      li.appendChild(b); ul.appendChild(li);
    });
    w.appendChild(ul);
  }else{
    w.appendChild(el("p","dica","Nenhuma remoção isolada resolve. Solte um bloqueio de horário ou aumente os dias de campus."));
  }
  box.appendChild(w);
}

/* ============================================================ panorama */

const CORES = ["#F4F6F9","#DCE6EC","#B8D4D2","#8FBFB3","#C9B37A","#C48A5E","#B3576A","#8E2547"];
function corCalor(v, pico){
  if(!v) return CORES[0];
  return CORES[Math.min(CORES.length-1, 1+Math.floor((v/pico)*(CORES.length-2)))];
}

async function carregarPanorama(){
  const box = $("#panorama-conteudo");
  try{
    const d = await api(`/api/panorama?periodo=${S.periodo}`);
    S.carregado.panorama = true;
    box.innerHTML = "";

    const est = d.estabilidade;
    const met = el("div","metricas");
    const m = (rot,val,sub)=>{ const x=el("div","metrica");
      x.appendChild(el("span","rot",rot)); x.appendChild(el("div","val",val));
      if(sub) x.appendChild(el("div","sub",sub)); return x; };
    const totalTurmas = d.por_departamento.reduce((a,b)=>a+b.turmas,0);
    const totalLot = d.por_departamento.reduce((a,b)=>a+b.lotadas,0);
    met.appendChild(m("turmas no período", num(totalTurmas)));
    met.appendChild(m("sem vaga", num(totalLot),
      (100*totalLot/Math.max(totalTurmas,1)).toFixed(1)+"% da oferta"));
    met.appendChild(m("disciplinas sem saída", num(d.sem_saida.length),
      "todas as turmas lotadas"));
    met.appendChild(m("salas em uso", num(d.salas.salas_distintas),
      num(d.salas.total_conflitos_de_sala)+" conflitos na base"));
    if(est.aplicavel)
      met.appendChild(m("estabilidade", est.taxa_estabilidade+"%",
        `${num(est.mesmo_horario)} de ${num(est.turmas_em_ambos)} turmas mantêm o horário`));
    box.appendChild(met);

    // mapa de calor
    const c1 = el("section","cartao");
    const h1 = document.createElement("header");
    h1.appendChild(el("h3",null,"Onde a oferta se concentra"));
    h1.appendChild(el("span","nota","turmas ocupando cada faixa de 30 min"));
    c1.appendChild(h1);
    const b1 = el("div","corpo");
    const env = el("div","calor-envelope");
    const g = el("div","calor");
    g.appendChild(el("div","cab",""));
    DIAS3.forEach(x=>g.appendChild(el("div","cab",x)));
    const mc = d.mapa_de_calor;
    for(let f=0; f<mc.fatias.length; f++){
      g.appendChild(el("div","hora", f%2===0 ? mc.fatias[f] : ""));
      for(let dia=0; dia<6; dia++){
        const v = mc.blocos[dia][f], lot = mc.lotadas[dia][f];
        const cel = el("div","cel");
        cel.style.background = corCalor(v, mc.pico||1);
        cel.title = `${DIAS[dia]} ${mc.fatias[f]}\n${v} turmas` +
                    (v?` · ${lot} sem vaga (${(100*lot/v).toFixed(0)}%)`:"");
        g.appendChild(cel);
      }
    }
    env.appendChild(g); b1.appendChild(env);
    const lg = el("div","legenda-calor");
    const rampa = el("div","rampa");
    CORES.forEach(c=>{ const i=document.createElement("i"); i.style.background=c; rampa.appendChild(i); });
    lg.appendChild(el("span",null,"vazio"));
    lg.appendChild(rampa);
    lg.appendChild(el("span",null,`pico: ${mc.pico} turmas na mesma faixa`));
    b1.appendChild(lg);
    c1.appendChild(b1); box.appendChild(c1);

    // por hora + por dia
    const dois = el("div","grade2");
    dois.appendChild(cartaoBarras("Taxa de lotação por hora de início",
      "quanto da oferta daquela faixa está sem vaga",
      d.por_hora.map(x=>({rot:x.hora, total:x.turmas, lot:x.lotadas,
                          fim:x.taxa_lotacao+"% lotadas"}))));
    dois.appendChild(cartaoBarras("Turmas por dia da semana",
      "uma turma conta em cada dia em que tem aula",
      d.por_dia.map(x=>({rot:x.dia.slice(0,3), total:x.turmas, lot:x.lotadas,
                          fim:num(x.turmas)+" turmas"}))));
    box.appendChild(dois);

    // departamentos
    box.appendChild(cartaoTabela("Departamentos", "ordenado por número de turmas",
      ["departamento","disciplinas","turmas","sem vaga","lotação","vagas"],
      d.por_departamento.map(x=>[x.departamento, num(x.disciplinas), num(x.turmas),
        num(x.lotadas), x.taxa_lotacao+"%", num(x.vagas)]), [0]));

    // conflitos internos da base
    const c3 = el("section","cartao");
    const h3 = document.createElement("header");
    h3.appendChild(el("h3",null,"Conflitos dentro da própria base"));
    h3.appendChild(el("span","nota","não são erro do sistema, são o que veio no arquivo"));
    c3.appendChild(h3);
    const b3 = el("div","corpo");
    b3.innerHTML = `<p class="dica" style="margin:0 0 10px">
      A base traz <b>${num(d.salas.total_conflitos_de_sala)}</b> casos de duas turmas na mesma
      sala, dia e hora, e <b>${num(d.professores.total_conflitos_de_professor)}</b> de um professor
      em dois lugares ao mesmo tempo. Isso significa que restrição de sala e de professor
      precisa ser tratada como flexível em qualquer reprogramação da oferta, e vale
      confirmar com a DSI se são exceções toleradas pelo SGU ou ruído de extração.
      A carga média de ${d.professores.carga_media_horas}h por professor é
      <b>subestimada</b>, porque orientação e TCC não têm horário no arquivo.</p>`;
    c3.appendChild(b3); box.appendChild(c3);

  }catch(e){ box.innerHTML = `<div class="placeholder">${e.message}</div>`; }
}

function cartaoBarras(titulo, nota, linhas){
  const c = el("section","cartao");
  const h = document.createElement("header");
  h.appendChild(el("h3",null,titulo));
  if(nota) h.appendChild(el("span","nota",nota));
  c.appendChild(h);
  const b = el("div","corpo");
  const wrap = el("div","barras");
  const pico = Math.max(...linhas.map(x=>x.total), 1);
  linhas.forEach(x=>{
    const li = el("div","barra-linha");
    li.appendChild(el("span","rot", x.rot));
    const tr = el("div","trilho");
    const t = document.createElement("i"); t.className="total";
    t.style.width = (100*(x.total-x.lot)/pico)+"%";
    const l = document.createElement("i"); l.className="lot";
    l.style.width = (100*x.lot/pico)+"%";
    tr.appendChild(l); tr.appendChild(t);
    li.appendChild(tr);
    li.appendChild(el("span","fim", x.fim));
    wrap.appendChild(li);
  });
  b.appendChild(wrap);
  b.appendChild(el("p","dica","A parte escura é a fração sem vaga."));
  c.appendChild(b); return c;
}

function cartaoTabela(titulo, nota, colunas, linhas, textoIdx=[]){
  const c = el("section","cartao");
  const h = document.createElement("header");
  h.appendChild(el("h3",null,titulo));
  if(nota) h.appendChild(el("span","nota",nota));
  c.appendChild(h);
  const rolar = el("div","rolar");
  const t = document.createElement("table");
  const thead = document.createElement("thead"); const tr = document.createElement("tr");
  colunas.forEach((x,i)=>{ const th=el("th", textoIdx.includes(i)?"":"num", x); tr.appendChild(th); });
  thead.appendChild(tr); t.appendChild(thead);
  const tb = document.createElement("tbody");
  linhas.forEach(linha=>{
    const r = document.createElement("tr");
    linha.forEach((v,i)=>{
      const td = document.createElement("td");
      if(!textoIdx.includes(i)) td.className="num";
      if(v instanceof Node) td.appendChild(v); else td.textContent = v;
      r.appendChild(td);
    });
    tb.appendChild(r);
  });
  t.appendChild(tb); rolar.appendChild(t); c.appendChild(rolar);
  return c;
}

/* ============================================================ vagas */

async function carregarVagas(){
  const box = $("#vagas-conteudo");
  try{
    const d = await api(`/api/risco?periodo=${S.periodo}`);
    const pan = await api(`/api/panorama?periodo=${S.periodo}`);
    S.carregado.vagas = true;
    box.innerHTML = "";

    box.appendChild(cartaoTabela(
      "Disciplinas sem saída",
      "todas as turmas estão sem vaga — quem precisa cursar agora não tem para onde ir",
      ["disciplina","depto","turmas","horários"],
      d.sem_saida.slice(0,60).map(x=>[x.nome, x.departamento, num(x.turmas),
        x.horarios.join(" | ")]), [0,1,3]));

    box.appendChild(cartaoTabela(
      "Turmas de disciplina única",
      "restrição rígida para quem precisa se formar; lotada, trava o curso",
      ["disciplina","turma","horário","vagas","situação"],
      pan.gargalos.map(x=>{
        const s = el("span", `selo n${x.lotada?4:1}`, x.lotada?"sem vaga":"tem vaga");
        return [x.nome, x.turma_id, x.horario, num(x.vagas), s];
      }), [0,1,2,4]));

    box.appendChild(cartaoTabela(
      "Turmas por risco de não conseguir a vaga",
      "saldo baixo em faixa concorrida sobe de nível",
      ["disciplina","turma","horário","vagas","risco","turmas da disciplina"],
      d.ranking.map(x=>{
        const s = el("span", `selo n${x.nivel}`, x.rotulo);
        return [x.nome, x.turma_id, x.horario, num(x.vagas), s, num(x.turmas_da_disciplina)];
      }), [0,1,2,4]));

  }catch(e){ box.innerHTML = `<div class="placeholder">${e.message}</div>`; }
}

/* ============================================================ conflitos */

async function carregarConflitos(){
  const box = $("#conflitos-conteudo");
  box.innerHTML = '<div class="carregando">calculando…</div>';
  try{
    const escopo = $("#cf-escopo").value, depto = $("#cf-depto").value, vaga = $("#cf-vaga").value;
    const d = await api(`/api/conflitos?periodo=${S.periodo}&escopo=${escopo}`
      + (depto?`&departamento=${encodeURIComponent(depto)}`:"") + `&com_vaga=${vaga}`);
    box.innerHTML = "";

    const met = el("div","metricas");
    const m=(r,v,s)=>{const x=el("div","metrica");x.appendChild(el("span","rot",r));
      x.appendChild(el("div","val",v)); if(s)x.appendChild(el("div","sub",s)); return x;};
    met.appendChild(m("pares impossíveis", num(d.pares_impossiveis)));
    met.appendChild(m("pares comparados", num(d.pares_comparados)));
    met.appendChild(m("disciplinas", num(d.disciplinas_avaliadas)));
    met.appendChild(m("tempo", d.ms+" ms", d.escopo));
    box.appendChild(met);

    box.appendChild(cartaoTabela(
      "Pares que nunca combinam",
      "ordenado pelo custo: pares com poucas turmas dos dois lados vêm primeiro",
      ["disciplina A","turmas","disciplina B","turmas","depto"],
      d.resultados.map(p=>[p.nome_a, num(p.turmas_a), p.nome_b, num(p.turmas_b), p.departamento]),
      [0,2,4]));

    if(d.truncado)
      box.appendChild(el("p","dica","O cálculo foi interrompido pelo limite de tempo; os resultados são parciais."));
  }catch(e){ box.innerHTML = `<div class="placeholder">${e.message}</div>`; }
}

/* ============================================================ dados */

async function carregarDados(){
  const box = $("#dados-conteudo");
  const d = S.base.resumo, est = S.base.estabilidade;
  S.carregado.dados = true;
  box.innerHTML = "";

  if(d.avisos?.length){
    const ul = el("ul","avisos");
    d.avisos.forEach(a=>{
      const li = document.createElement("li");
      if(/zero vagas|saldo/.test(a)) li.className = "grave";
      li.textContent = a;
      ul.appendChild(li);
    });
    box.appendChild(ul);
  }

  const met = el("div","metricas");
  const m=(r,v,s)=>{const x=el("div","metrica");x.appendChild(el("span","rot",r));
    x.appendChild(el("div","val",v)); if(s)x.appendChild(el("div","sub",s)); return x;};
  met.appendChild(m("linhas lidas", num(d.linhas_lidas), d.arquivo_turmas));
  met.appendChild(m("blocos distintos", num(d.linhas_unicas), d.fator_duplicacao+"x de duplicação"));
  met.appendChild(m("turmas", num(d.turmas), num(d.turmas_lotadas)+" sem vaga"));
  met.appendChild(m("disciplinas ofertadas", num(d.disciplinas_ofertadas),
    num(d.disciplinas_sem_ficha)+" sem ficha no catálogo"));
  box.appendChild(met);

  box.appendChild(cartaoTabela("O que foi lido e o que foi descartado", null,
    ["item","valor"],
    [["Arquivo de oferta", d.arquivo_turmas],
     ["Arquivo de disciplinas", d.arquivo_disciplinas || "(não informado)"],
     ["Períodos encontrados", d.periodos.join(", ")],
     ["Linhas no arquivo", num(d.linhas_lidas)],
     ["Blocos distintos depois de deduplicar", num(d.linhas_unicas)],
     ["Fator de duplicação", d.fator_duplicacao+"x"],
     ["Linhas sem dia ou hora (TCC, orientação, estágio)", num(d.descartadas_sem_horario)],
     ["Linhas com hora inválida", num(d.descartadas_hora_invalida)],
     ["Blocos adjacentes fundidos num só", num(d.blocos_fundidos)],
     ["Turmas montadas", num(d.turmas)],
     ["Turmas com zero vagas", num(d.turmas_lotadas)],
     ["Turmas com vagas divergentes entre linhas", num(d.turmas_vagas_inconsistentes)],
     ["Disciplinas na oferta", num(d.disciplinas_ofertadas)],
     ["Disciplinas no catálogo", num(d.disciplinas_no_catalogo)],
     ["Ofertadas sem ficha no catálogo", num(d.disciplinas_sem_ficha)],
     ["No catálogo sem oferta", num(d.catalogo_sem_oferta)],
    ], [0,1]));

  if(est.aplicavel){
    box.appendChild(cartaoTabela("Estabilidade entre os períodos",
      "quantas turmas mantêm exatamente o mesmo horário",
      ["item","valor"],
      [[`Turmas em ${est.periodo_a}`, num(est.turmas_a)],
       [`Turmas em ${est.periodo_b}`, num(est.turmas_b)],
       ["Presentes nos dois", num(est.turmas_em_ambos)],
       ["Com o mesmo horário", num(est.mesmo_horario)],
       ["Taxa de estabilidade", est.taxa_estabilidade+"%"],
       [`Só em ${est.periodo_a}`, num(est.so_em_a)],
       [`Só em ${est.periodo_b}`, num(est.so_em_b)],
      ], [0,1]));

    const c = el("section","cartao");
    const h = document.createElement("header"); h.appendChild(el("h3",null,"Como ler esse número"));
    c.appendChild(h);
    const b = el("div","corpo");
    b.innerHTML = `<p class="dica" style="margin:0">
      A taxa de estabilidade é a informação mais política do pacote. Com
      <b>${est.taxa_estabilidade}%</b>, boa parte da oferta repete o mesmo horário de um
      período para o outro. Quanto mais alta, menos realista é propor reprogramar horários
      existentes, e mais o caminho passa a ser abrir turma nova nas faixas com folga em vez
      de mover turma consolidada.</p>`;
    c.appendChild(b); box.appendChild(c);
  }
}

iniciar().catch(e=>{
  $("#estado-base").textContent = "erro: "+e.message;
});
