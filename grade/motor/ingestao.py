"""
Ingestao da oferta a partir dos CSVs do SGU.

Este modulo existe porque a base real tem quatro caracteristicas que quebram
uma leitura ingenua. Todas foram medidas nos arquivos de producao:

1. LINHAS DUPLICADAS — 74.381 linhas para 26.655 blocos distintos (2,8x).
   O mesmo bloco se repete de 2 a 19 vezes. Sem deduplicar, toda contagem
   sai inflada e a grade desenha a mesma aula varias vezes sobreposta.

2. 'vagas' E SALDO, NAO CAPACIDADE — mediana 3, maximo 56, e 19,5% das
   turmas em zero. Capacidade nunca seria zero. Entao vagas e o numero de
   lugares ainda abertos no momento do export, o que vira sinal de procura
   direto. O valor tambem oscila entre as linhas duplicadas da mesma turma
   (9, 9, 10, 9...) sem tendencia, entao usamos a MODA.

3. CATALOGO INCOMPLETO — 1.825 disciplinas aparecem na oferta, mas
   disciplinas.csv descreve so 1.017. Nome e creditos caem para o que vem
   em turmas_horarios.csv quando falta a ficha.

4. DEPARTAMENTO CODIFICADO DIFERENTE — disciplinas.csv usa codigo numerico
   (731, 634), turmas_horarios.csv usa sigla (COM, JUR). Nao se juntam.
   Vale a sigla da oferta.

Alem disso, blocos adjacentes da mesma turma, dia e sala sao fundidos
(13:00-16:00 + 16:00-19:00 vira 13:00-19:00).
"""

from __future__ import annotations

import csv
import io
import unicodedata
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path

from .mascara import INDICE_DIA, mascara_bloco, para_minutos


def _sem_acento(t: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", t)
                   if unicodedata.category(c) != "Mn")


def _chave(nome: str) -> str:
    return _sem_acento((nome or "").strip().lower()).replace(" ", "_")


ALIAS = {
    "periodo": {"periodo", "periodo_letivo", "ano_semestre", "semestre"},
    "turma_id": {"turma_id", "id_turma", "codigo_turma"},
    "cod_disciplina": {"cod_disciplina", "codigo_disciplina", "disciplina_id"},
    "turma": {"turma", "cod_turma"},
    "disciplina_abrev": {"disciplina_abrev", "disciplina", "nome_disciplina"},
    "dia_semana": {"dia_semana", "dia", "diadasemana"},
    "hora_inicio": {"hora_inicio", "inicio", "hora_ini"},
    "hora_fim": {"hora_fim", "fim", "hora_termino"},
    "sala_id": {"sala_id", "sala", "local"},
    "vagas": {"vagas", "vagas_restantes", "saldo"},
    "creditos": {"creditos", "credito", "ch"},
    "professor_id": {"professor_id", "professor", "docente_id"},
    "cod_departamento": {"cod_departamento", "departamento", "depto"},
    "horas_teoria": {"horas_teoria", "ch_teorica"},
    "horas_pratica": {"horas_pratica", "ch_pratica"},
}


def _mapear(cabecalho) -> dict[str, str]:
    mapa = {}
    for coluna in cabecalho:
        k = _chave(coluna)
        for canonico, variantes in ALIAS.items():
            if k in variantes and canonico not in mapa:
                mapa[canonico] = coluna
                break
    return mapa


def _ler_csv(caminho: Path):
    bruto = caminho.read_bytes()
    texto = None
    for cod in ("utf-8-sig", "utf-8", "latin-1", "cp1252"):
        try:
            texto = bruto.decode(cod)
            break
        except UnicodeDecodeError:
            continue
    if texto is None:
        raise ValueError(f"nao consegui decodificar {caminho.name}")
    try:
        delim = csv.Sniffer().sniff(texto[:8192], delimiters=",;\t|").delimiter
    except csv.Error:
        delim = ","
    linhas = list(csv.DictReader(io.StringIO(texto), delimiter=delim))
    if not linhas:
        raise ValueError(f"{caminho.name} nao tem linhas de dados")
    return linhas, _mapear(linhas[0].keys())


def _inteiro(v, padrao: int = 0) -> int:
    try:
        return int(str(v).strip().split(".")[0])
    except (TypeError, ValueError, AttributeError):
        return padrao


@dataclass(frozen=True)
class Bloco:
    dia: str
    dia_idx: int
    hora_inicio: str
    hora_fim: str
    sala_id: str

    @property
    def minutos(self) -> int:
        return para_minutos(self.hora_fim) - para_minutos(self.hora_inicio)


@dataclass
class Turma:
    periodo: int
    turma_id: str
    cod_disciplina: str
    turma: str
    nome: str
    creditos: int
    vagas: int                       # saldo disponivel, nao capacidade
    professores: list[str]
    salas: list[str]
    cod_departamento: str
    blocos: list[Bloco] = field(default_factory=list)
    mascara: int = 0

    @property
    def chave(self):
        return (self.periodo, self.turma_id)

    @property
    def lotada(self) -> bool:
        return self.vagas <= 0

    @property
    def minutos_semana(self) -> int:
        return sum(b.minutos for b in self.blocos)

    def horario_legivel(self) -> str:
        return "; ".join(f"{b.dia[:3]} {b.hora_inicio}-{b.hora_fim}"
                         for b in sorted(self.blocos, key=lambda x: (x.dia_idx, x.hora_inicio)))


@dataclass
class Relatorio:
    arquivo_turmas: str = ""
    arquivo_disciplinas: str = ""
    linhas_lidas: int = 0
    linhas_unicas: int = 0
    descartadas_sem_horario: int = 0
    descartadas_hora_invalida: int = 0
    blocos_fundidos: int = 0
    turmas: int = 0
    disciplinas_ofertadas: int = 0
    disciplinas_no_catalogo: int = 0
    disciplinas_sem_ficha: int = 0
    catalogo_sem_oferta: int = 0
    turmas_vagas_inconsistentes: int = 0
    avisos: list[str] = field(default_factory=list)

    @property
    def fator_duplicacao(self) -> float:
        return self.linhas_lidas / self.linhas_unicas if self.linhas_unicas else 1.0


class Catalogo:
    OBRIGATORIAS = ["periodo", "turma_id", "cod_disciplina",
                    "dia_semana", "hora_inicio", "hora_fim"]

    def __init__(self, caminho_turmas, caminho_disciplinas=None):
        self.relatorio = Relatorio()
        self.fichas: dict[str, dict] = {}
        self.turmas: dict[tuple[int, str], Turma] = {}
        self.por_disciplina: dict[tuple[int, str], list[Turma]] = defaultdict(list)
        self.periodos: list[int] = []
        if caminho_disciplinas and Path(caminho_disciplinas).exists():
            self._ler_fichas(Path(caminho_disciplinas))
        self._ler_turmas(Path(caminho_turmas))
        self._finalizar()

    def _ler_fichas(self, caminho: Path) -> None:
        linhas, mapa = _ler_csv(caminho)
        self.relatorio.arquivo_disciplinas = caminho.name

        def col(l, campo, padrao=""):
            return l.get(mapa[campo], padrao) if campo in mapa else padrao

        for l in linhas:
            cod = (col(l, "cod_disciplina") or "").strip()
            if not cod:
                continue
            self.fichas[cod] = {
                "nome": (col(l, "disciplina_abrev") or "").strip(),
                "creditos": _inteiro(col(l, "creditos")),
                "horas_teoria": _inteiro(col(l, "horas_teoria")),
                "horas_pratica": _inteiro(col(l, "horas_pratica")),
                "cod_departamento": (col(l, "cod_departamento") or "").strip(),
            }
        self.relatorio.disciplinas_no_catalogo = len(self.fichas)

    def _ler_turmas(self, caminho: Path) -> None:
        linhas, mapa = _ler_csv(caminho)
        r = self.relatorio
        r.arquivo_turmas = caminho.name
        r.linhas_lidas = len(linhas)

        faltando = [c for c in self.OBRIGATORIAS if c not in mapa]
        if faltando:
            raise ValueError(f"faltam colunas em {caminho.name}: {', '.join(faltando)}")

        def col(l, campo, padrao=""):
            return l.get(mapa[campo], padrao) if campo in mapa else padrao

        vistos: set = set()
        blocos_por_turma: dict = defaultdict(set)
        attr: dict = defaultdict(lambda: {
            "vagas": [], "prof": [], "sala": [], "cr": [],
            "nome": [], "dep": [], "turma": [], "cod": [],
        })

        for l in linhas:
            per = _inteiro(col(l, "periodo"))
            tid = (col(l, "turma_id") or "").strip()
            cod = (col(l, "cod_disciplina") or "").strip()
            if not (per and tid and cod):
                continue

            k = (per, tid)
            a = attr[k]
            a["cod"].append(cod)
            a["vagas"].append(_inteiro(col(l, "vagas"), -1))
            a["prof"].append((col(l, "professor_id") or "").strip())
            a["sala"].append((col(l, "sala_id") or "").strip())
            a["cr"].append(_inteiro(col(l, "creditos")))
            a["nome"].append((col(l, "disciplina_abrev") or "").strip())
            a["dep"].append((col(l, "cod_departamento") or "").strip())
            a["turma"].append((col(l, "turma") or "").strip())

            dia = (col(l, "dia_semana") or "").strip()
            ini = (col(l, "hora_inicio") or "").strip()
            fim = (col(l, "hora_fim") or "").strip()
            # TCC, orientacao e estagio nao tem horario para alocar
            if not (dia and ini and fim) or dia not in INDICE_DIA:
                r.descartadas_sem_horario += 1
                continue
            try:
                if para_minutos(fim) <= para_minutos(ini):
                    r.descartadas_hora_invalida += 1
                    continue
            except (ValueError, AttributeError):
                r.descartadas_hora_invalida += 1
                continue

            sala = (col(l, "sala_id") or "").strip()
            assinatura = (per, tid, dia, ini, fim, sala)
            if assinatura in vistos:
                continue
            vistos.add(assinatura)
            blocos_por_turma[k].add((dia, ini, fim, sala))

        r.linhas_unicas = len(vistos)

        def moda(vals, padrao=""):
            filtrados = [v for v in vals if v not in ("", None)]
            return Counter(filtrados).most_common(1)[0][0] if filtrados else padrao

        for k, brutos in blocos_por_turma.items():
            per, tid = k
            a = attr[k]

            vagas_validas = [v for v in a["vagas"] if v >= 0]
            if len(set(vagas_validas)) > 1:
                r.turmas_vagas_inconsistentes += 1
            vagas = Counter(vagas_validas).most_common(1)[0][0] if vagas_validas else 0

            cod = moda(a["cod"], tid)
            ficha = self.fichas.get(cod, {})
            nome = ficha.get("nome") or moda(a["nome"], cod)
            creditos = ficha.get("creditos") or _inteiro(moda([c for c in a["cr"] if c], 0))

            blocos = self._fundir(brutos)
            mascara = 0
            for b in blocos:
                mascara |= mascara_bloco(b.dia, b.hora_inicio, b.hora_fim)

            t = Turma(
                periodo=per, turma_id=tid, cod_disciplina=cod,
                turma=moda(a["turma"]), nome=nome, creditos=creditos, vagas=vagas,
                professores=sorted({p for p in a["prof"] if p}),
                salas=sorted({s for s in a["sala"] if s}),
                cod_departamento=moda(a["dep"]),
                blocos=blocos, mascara=mascara,
            )
            self.turmas[k] = t
            self.por_disciplina[(per, cod)].append(t)

    def _fundir(self, brutos: set) -> list[Bloco]:
        por_dia_sala: dict = defaultdict(list)
        for dia, ini, fim, sala in brutos:
            por_dia_sala[(dia, sala)].append((ini, fim))

        saida: list[Bloco] = []
        for (dia, sala), faixas in por_dia_sala.items():
            faixas.sort(key=lambda f: para_minutos(f[0]))
            ini_at, fim_at = faixas[0]
            for ini, fim in faixas[1:]:
                if para_minutos(ini) <= para_minutos(fim_at):
                    if para_minutos(ini) == para_minutos(fim_at):
                        self.relatorio.blocos_fundidos += 1
                    fim_at = max(fim_at, fim, key=para_minutos)
                else:
                    saida.append(Bloco(dia, INDICE_DIA[dia], ini_at, fim_at, sala))
                    ini_at, fim_at = ini, fim
            saida.append(Bloco(dia, INDICE_DIA[dia], ini_at, fim_at, sala))
        return sorted(saida, key=lambda b: (b.dia_idx, b.hora_inicio))

    def _finalizar(self) -> None:
        r = self.relatorio
        self.periodos = sorted({p for p, _ in self.turmas})
        r.turmas = len(self.turmas)
        ofertadas = {c for _, c in self.por_disciplina}
        r.disciplinas_ofertadas = len(ofertadas)
        r.disciplinas_sem_ficha = len(ofertadas - set(self.fichas))
        r.catalogo_sem_oferta = len(set(self.fichas) - ofertadas)

        if r.fator_duplicacao > 1.05:
            r.avisos.append(
                f"O arquivo traz {r.linhas_lidas:,} linhas para {r.linhas_unicas:,} blocos "
                f"distintos ({r.fator_duplicacao:.1f}x). As repeticoes foram descartadas."
                .replace(",", ".")
            )
        if r.disciplinas_sem_ficha:
            r.avisos.append(
                f"{r.disciplinas_sem_ficha} disciplinas ofertadas nao tem ficha em "
                f"{r.arquivo_disciplinas or 'disciplinas.csv'}. Nome e creditos vieram da oferta."
            )
        if r.turmas_vagas_inconsistentes:
            r.avisos.append(
                f"{r.turmas_vagas_inconsistentes} turmas trazem mais de um valor de vagas "
                "entre suas linhas. Foi usado o valor mais frequente."
            )
        lotadas = sum(1 for t in self.turmas.values() if t.lotada)
        if lotadas:
            r.avisos.append(
                f"{lotadas} turmas estao com zero vagas, o que indica que 'vagas' e saldo "
                "disponivel e nao capacidade. Confirme a data do export com a DSI."
            )

    # ---------- consultas ----------

    def turmas_de(self, periodo: int, cod: str) -> list[Turma]:
        return self.por_disciplina.get((periodo, cod), [])

    def nome(self, periodo: int, cod: str) -> str:
        t = self.turmas_de(periodo, cod)
        return t[0].nome if t else self.fichas.get(cod, {}).get("nome", cod)

    def disciplinas(self, periodo: int) -> list[dict]:
        saida = []
        for (per, cod), turmas in self.por_disciplina.items():
            if per != periodo or not turmas:
                continue
            abertas = [t for t in turmas if not t.lotada]
            saida.append({
                "cod_disciplina": cod,
                "nome": turmas[0].nome,
                "creditos": turmas[0].creditos,
                "departamento": turmas[0].cod_departamento,
                "turmas": len(turmas),
                "turmas_abertas": len(abertas),
                "turma_unica": len(turmas) == 1,
                "sem_vaga": not abertas,
                "vagas_totais": sum(t.vagas for t in turmas),
            })
        saida.sort(key=lambda d: d["nome"])
        return saida

    def resumo(self) -> dict:
        r = self.relatorio
        return {
            "arquivo_turmas": r.arquivo_turmas,
            "arquivo_disciplinas": r.arquivo_disciplinas,
            "periodos": self.periodos,
            "linhas_lidas": r.linhas_lidas,
            "linhas_unicas": r.linhas_unicas,
            "fator_duplicacao": round(r.fator_duplicacao, 2),
            "descartadas_sem_horario": r.descartadas_sem_horario,
            "descartadas_hora_invalida": r.descartadas_hora_invalida,
            "blocos_fundidos": r.blocos_fundidos,
            "turmas": r.turmas,
            "turmas_lotadas": sum(1 for t in self.turmas.values() if t.lotada),
            "disciplinas_ofertadas": r.disciplinas_ofertadas,
            "disciplinas_no_catalogo": r.disciplinas_no_catalogo,
            "disciplinas_sem_ficha": r.disciplinas_sem_ficha,
            "catalogo_sem_oferta": r.catalogo_sem_oferta,
            "turmas_vagas_inconsistentes": r.turmas_vagas_inconsistentes,
            "avisos": r.avisos,
        }
