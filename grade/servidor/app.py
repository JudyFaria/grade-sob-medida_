"""
Servidor local. Biblioteca padrao do Python apenas — nenhum pip install.

Carrega os CSVs uma vez na subida e mantem o catalogo em memoria. Para a
escala desta base (74 mil linhas, 4.947 turmas) isso ocupa poucas dezenas de
MB e dispensa banco de dados.

O estado vivo e um so: as intencoes registradas quando o aluno exporta um
plano. Ele mora em memoria e se perde ao reiniciar, o que e adequado para
uma aplicacao de apresentacao. Persistir isso e o primeiro passo se o
sistema virar servico de verdade.
"""

from __future__ import annotations

import json
import mimetypes
import threading
import traceback
from dataclasses import replace
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from motor import (
    Bloqueio, Catalogo, FormatoDia, Preferencias, Risco,
    buscar, diagnosticar, diversificar, nao_dominadas, rotular,
    pares_impossiveis, vizinhos,
)
from motor import panorama
from motor.pontuacao import explicar

RAIZ = Path(__file__).resolve().parent.parent
WEB = RAIZ / "web"

ESTADO: dict = {}
TRAVA = threading.Lock()


def carregar(caminho_turmas: Path, caminho_disciplinas: Path) -> None:
    catalogo = Catalogo(caminho_turmas, caminho_disciplinas)
    ESTADO["catalogo"] = catalogo
    ESTADO["risco"] = Risco(catalogo)
    ESTADO["cache_conflitos"] = {}


# ------------------------------------------------------------------ helpers


def _pref(corpo: dict) -> Preferencias:
    f = corpo.get("formato") or {}
    return Preferencias(
        periodo=int(corpo["periodo"]),
        desejadas=list(corpo.get("desejadas") or []),
        obrigatorias=set(corpo.get("obrigatorias") or []),
        min_disciplinas=corpo.get("min_disciplinas"),
        bloqueios=[
            Bloqueio(b.get("rotulo", "indisponivel"), b["dias"], b["hora_inicio"], b["hora_fim"])
            for b in (corpo.get("bloqueios") or [])
        ],
        formato=FormatoDia(
            inicio_mais_cedo=f.get("inicio_mais_cedo", "07:00"),
            fim_mais_tarde=f.get("fim_mais_tarde", "23:00"),
            max_aulas_seguidas=int(f.get("max_aulas_seguidas", 3)),
            intervalo_desejado_min=int(f.get("intervalo_desejado_min", 0)),
            intervalo_tolerado_max=int(f.get("intervalo_tolerado_max", 240)),
            max_dias_campus=int(f.get("max_dias_campus", 6)),
        ),
        creditos_min=int(corpo.get("creditos_min", 0)),
        creditos_max=int(corpo.get("creditos_max", 99)),
        evitar_turmas=set(corpo.get("evitar_turmas") or []),
        incluir_lotadas=bool(corpo.get("incluir_lotadas", False)),
    )


def _turma_json(t, risco: Risco) -> dict:
    d = risco.descrever(t)
    return {
        "turma_id": t.turma_id,
        "cod_disciplina": t.cod_disciplina,
        "nome": t.nome,
        "turma": t.turma,
        "creditos": t.creditos,
        "departamento": t.cod_departamento,
        "horario": t.horario_legivel(),
        "salas": t.salas,
        "professores": len(t.professores),
        "blocos": [
            {"dia": b.dia, "dia_idx": b.dia_idx, "inicio": b.hora_inicio,
             "fim": b.hora_fim, "sala": b.sala_id}
            for b in t.blocos
        ],
        **d,
    }


def _plano_texto(grade, risco: Risco, catalogo) -> str:
    ordem = sorted(grade.turmas, key=lambda t: t.vagas)
    linhas = ["Plano de matricula", ""]
    for i, t in enumerate(ordem, 1):
        resto = 0
        for o in grade.turmas:
            if o.turma_id != t.turma_id:
                resto |= o.mascara
        suplentes = [
            a.turma_id for a in catalogo.turmas_de(t.periodo, t.cod_disciplina)
            if a.turma_id != t.turma_id and not a.lotada and not (a.mascara & resto)
        ][:2]
        linha = f"{i}. {t.turma_id}  {t.nome} ({t.horario_legivel()})  [{t.vagas} vagas]"
        if suplentes:
            linha += f"\n   suplente: {', '.join(suplentes)}"
        linhas.append(linha)
    linhas += [
        "",
        f"Total: {grade.creditos} creditos",
        "Ordem sugerida: da turma com menos vagas para a com mais.",
        "Este plano nao reserva vaga. As vagas mostradas sao as do momento do export.",
    ]
    return "\n".join(linhas)


# ------------------------------------------------------------------ rotas


def rota_base(_q) -> dict:
    c = ESTADO["catalogo"]
    return {"resumo": c.resumo(), "estabilidade": panorama.estabilidade(c)}


def rota_disciplinas(q) -> dict:
    c = ESTADO["catalogo"]
    periodo = int(q.get("periodo", [c.periodos[-1]])[0])
    termo = (q.get("q", [""])[0] or "").strip().lower()
    depto = (q.get("departamento", [""])[0] or "").strip()
    limite = int(q.get("limite", ["40"])[0])

    itens = c.disciplinas(periodo)
    if depto:
        itens = [d for d in itens if d["departamento"] == depto]
    if termo:
        itens = [d for d in itens
                 if termo in d["nome"].lower() or termo in d["cod_disciplina"].lower()]
    return {"periodo": periodo, "total": len(itens), "itens": itens[:limite]}


def rota_panorama(q) -> dict:
    c = ESTADO["catalogo"]
    periodo = int(q.get("periodo", [c.periodos[-1]])[0])
    return {
        "periodo": periodo,
        "mapa_de_calor": panorama.mapa_de_calor(c, periodo),
        "por_hora": panorama.por_hora_inicio(c, periodo),
        "por_dia": panorama.por_dia(c, periodo),
        "por_departamento": panorama.por_departamento(c, periodo),
        "gargalos": panorama.gargalos(c, periodo),
        "salas": panorama.salas(c, periodo),
        "professores": panorama.professores(c, periodo),
        "estabilidade": panorama.estabilidade(c),
        "sem_saida": ESTADO["risco"].disciplinas_sem_saida(periodo),
    }


def rota_risco(q) -> dict:
    c = ESTADO["catalogo"]
    periodo = int(q.get("periodo", [c.periodos[-1]])[0])
    r = ESTADO["risco"]
    return {
        "periodo": periodo,
        "ranking": r.ranking(periodo, int(q.get("limite", ["60"])[0])),
        "sem_saida": r.disciplinas_sem_saida(periodo),
    }


def rota_conflitos(q) -> dict:
    c = ESTADO["catalogo"]
    periodo = int(q.get("periodo", [c.periodos[-1]])[0])
    escopo = q.get("escopo", ["departamento"])[0]
    depto = (q.get("departamento", [""])[0] or "") or None
    com_vaga = q.get("com_vaga", ["1"])[0] != "0"

    chave = (periodo, escopo, depto, com_vaga)
    cache = ESTADO["cache_conflitos"]
    if chave not in cache:
        cache[chave] = pares_impossiveis(
            c, periodo,
            mesmo_departamento=(escopo == "departamento"),
            apenas_com_vaga=com_vaga,
            departamento=depto,
        )
    return cache[chave]


def rota_vizinhos(q) -> dict:
    c = ESTADO["catalogo"]
    periodo = int(q.get("periodo", [c.periodos[-1]])[0])
    cod = q.get("cod", [""])[0]
    return vizinhos(c, periodo, cod, q.get("com_vaga", ["1"])[0] != "0")


def rota_grades(corpo: dict) -> dict:
    c, r = ESTADO["catalogo"], ESTADO["risco"]
    if not corpo.get("desejadas"):
        return {"erro": "Escolha pelo menos uma disciplina."}

    pref = _pref(corpo)
    res = buscar(c, pref, r)

    if not res.total:
        return {"viavel": False, "ms": res.ms,
                "diagnostico": diagnosticar(c, pref, r), "cortes": res.cortes}

    front = nao_dominadas(res.grades)
    escolhidas = diversificar(front, r, int(corpo.get("quantidade", 4)),
                              semente=corpo.get("semente"))

    opcoes = []
    for grade, rot in rotular(escolhidas):
        opcoes.append({
            "rotulo": rot,
            "creditos": grade.creditos,
            "dias_campus": grade.dias_campus,
            "minutos_lacuna": grade.minutos_lacuna,
            "aderencia": grade.aderencia,
            "risco": grade.risco,
            "pior_risco": grade.pior_risco,
            "vagas_minimas": grade.vagas_minimas,
            "porque": explicar(grade.detalhes["avaliacao"]),
            "turmas": [_turma_json(t, r) for t in grade.turmas],
            "texto": _plano_texto(grade, r, c),
        })

    return {
        "viavel": True, "total_viaveis": res.total, "truncado": res.truncado,
        "ms": res.ms, "pareto": len(front),
        "turmas_por_disciplina": res.turmas_por_disciplina,
        "cortes": res.cortes, "opcoes": opcoes,
    }


def rota_planos(corpo: dict) -> dict:
    with TRAVA:
        ESTADO["risco"].registrar_plano(
            int(corpo["periodo"]), list(corpo.get("turma_ids") or [])
        )
        ESTADO["cache_conflitos"].clear()
    return {"registrado": len(corpo.get("turma_ids") or [])}


ROTAS_GET = {
    "/api/base": rota_base,
    "/api/disciplinas": rota_disciplinas,
    "/api/panorama": rota_panorama,
    "/api/risco": rota_risco,
    "/api/conflitos": rota_conflitos,
    "/api/conflitos/vizinhos": rota_vizinhos,
}
ROTAS_POST = {
    "/api/grades": rota_grades,
    "/api/planos": rota_planos,
}


# ------------------------------------------------------------------ handler


class Handler(BaseHTTPRequestHandler):
    server_version = "GradeSobMedida/1.0"

    def log_message(self, formato, *args):
        if "/api/" in (args[0] if args else ""):
            print(f"  {args[0]}")

    def _responder(self, codigo: int, corpo: bytes, tipo: str) -> None:
        self.send_response(codigo)
        self.send_header("Content-Type", tipo)
        self.send_header("Content-Length", str(len(corpo)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(corpo)

    def _json(self, dados, codigo: int = 200) -> None:
        self._responder(codigo, json.dumps(dados, ensure_ascii=False).encode("utf-8"),
                        "application/json; charset=utf-8")

    def do_GET(self):
        url = urlparse(self.path)
        caminho = url.path

        if caminho in ROTAS_GET:
            try:
                self._json(ROTAS_GET[caminho](parse_qs(url.query)))
            except Exception as e:
                traceback.print_exc()
                self._json({"erro": str(e)}, 500)
            return

        # arquivos estaticos
        rel = "index.html" if caminho == "/" else caminho.lstrip("/")
        alvo = (WEB / rel).resolve()
        if not str(alvo).startswith(str(WEB.resolve())) or not alvo.is_file():
            self._json({"erro": "nao encontrado"}, 404)
            return
        tipo = mimetypes.guess_type(str(alvo))[0] or "application/octet-stream"
        if tipo.startswith("text/") or tipo.endswith("javascript"):
            tipo += "; charset=utf-8"
        self._responder(200, alvo.read_bytes(), tipo)

    def do_POST(self):
        caminho = urlparse(self.path).path
        if caminho not in ROTAS_POST:
            self._json({"erro": "nao encontrado"}, 404)
            return
        try:
            tamanho = int(self.headers.get("Content-Length", 0))
            corpo = json.loads(self.rfile.read(tamanho) or b"{}")
            self._json(ROTAS_POST[caminho](corpo))
        except Exception as e:
            traceback.print_exc()
            self._json({"erro": str(e)}, 500)


def servir(porta: int = 8000) -> ThreadingHTTPServer:
    servidor = ThreadingHTTPServer(("127.0.0.1", porta), Handler)
    return servidor
