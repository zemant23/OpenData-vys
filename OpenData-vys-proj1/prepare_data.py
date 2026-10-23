#!/usr/bin/env python3
"""
prepare_data.py - spojí dva (a více) nesouvisející datasety z data.gov.cz po okresech.

  1) data/nadeje_doziti.csv   naděje dožití v okresech (ČSÚ)
  2) data/kultura/*.csv       kulturní místa (kina, muzea, památky...); každý soubor = jeden typ
  3) data/obyvatele.csv       (nepovinné) počet obyvatel okresů, kvůli přepočtu na 10 000 obyvatel

Výsledek: web/data.js  (načítají ho obě webové stránky)

Spuštění:   python3 prepare_data.py
Skript vypisuje, co v souborech našel. Pokud něco nenajde, napíše přesně co a jak to opravit.
"""
import glob
import json
import os
import re
import sys
import unicodedata

import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
F_DOZITI = os.path.join(HERE, "data", "nadeje_doziti.csv")
D_KULTURA = os.path.join(HERE, "data", "kultura")
F_OBYVATELE = os.path.join(HERE, "data", "obyvatele.csv")
OUT = os.path.join(HERE, "web", "data.js")

# ---- NASTAVENÍ (kdyby se sloupce v souborech jmenovaly jinak, přepište je tady) ----
# None = skript se pokusí sloupec najít sám podle názvu
COL_DOZITI_HODNOTA = None   # sloupec s počtem let, např. "hodnota"
COL_DOZITI_OKRES = None     # sloupec s názvem okresu, např. "uzemi_txt"
COL_DOZITI_POHLAVI = None   # sloupec s pohlavím, např. "pohlavi_txt"
COL_DOZITI_VEK = None       # sloupec s věkem, např. "vek_txt" nebo "vek_kod"
COL_DOZITI_OBDOBI = None    # sloupec s obdobím, např. "casref_do"
COL_KULTURA_OKRES = None    # sloupec s okresem v kulturních souborech
COL_OBYV_OKRES = None
COL_OBYV_POCET = None
# True = do analýzy se vezmou jen okresy, které mají v kulturních datech aspoň jeden záznam.
# Důležité, když kulturní data pokrývají jen některé kraje (jinak by ostatní okresy vyšly s nulou kultury).
JEN_OKRESY_S_KULTUROU = True
# Kategorie z NPÚ, které se nepočítají (jsou to jen části jiných památek nebo území)
VYLOUCIT_KATEGORIE = ["část objektu", "území"]
# -------------------------------------------------------------------------------


def bez_diakritiky(s):
    s = unicodedata.normalize("NFKD", str(s))
    return "".join(c for c in s if not unicodedata.combining(c))


def klic(s):
    """Sjednotí název okresu, aby šel spojit mezi soubory ('Okres Brno-město' == 'brno mesto')."""
    s = bez_diakritiky(s).lower().strip()
    s = re.sub(r"^okres\s+", "", s)
    s = re.sub(r"[^a-z0-9]+", " ", s).strip()
    return s


def konec(msg):
    print("\nCHYBA: " + msg)
    sys.exit(1)


def nacti_csv(cesta):
    for enc in ("utf-8-sig", "cp1250", "latin-1"):
        try:
            return pd.read_csv(cesta, sep=None, engine="python", encoding=enc, dtype=str)
        except (UnicodeDecodeError, pd.errors.ParserError):
            continue
        except Exception as e:  # prázdný soubor apod.
            konec(f"Soubor {cesta} nejde přečíst: {e}")
    konec(f"Soubor {cesta} nejde přečíst (neznámé kódování).")


def najdi(df, nastaveny, *slova, povinny=True, popis=""):
    if nastaveny:
        if nastaveny not in df.columns:
            konec(f"Sloupec '{nastaveny}' v souboru není. Sloupce jsou: {list(df.columns)}")
        return nastaveny
    for slovo in slova:
        for c in df.columns:
            if slovo in bez_diakritiky(c).lower():
                return c
    if povinny:
        konec(f"Nenašel jsem sloupec pro {popis}. Sloupce v souboru: {list(df.columns)}\n"
              f"Doplňte jeho název do NASTAVENÍ na začátku prepare_data.py.")
    return None


def cislo(s):
    return pd.to_numeric(s.astype(str).str.replace(",", ".", regex=False).str.replace(r"\s", "", regex=True),
                         errors="coerce")


# ------------------------------------------------------------------ naděje dožití
def zpracuj_doziti():
    if not os.path.exists(F_DOZITI):
        konec(f"Chybí soubor {F_DOZITI}")
    df = nacti_csv(F_DOZITI)
    print(f"[dožití] řádků: {len(df)}, sloupce: {list(df.columns)}")

    c_hod = najdi(df, COL_DOZITI_HODNOTA, "hodnota", popis="hodnotu (počet let)")
    c_okr = najdi(df, COL_DOZITI_OKRES, "vuzemi_txt", "uzemi_txt", "okres", "uzemi", popis="název okresu")
    c_poh = najdi(df, COL_DOZITI_POHLAVI, "pohlavi_txt", "pohlavi", popis="pohlaví")
    c_vek = najdi(df, COL_DOZITI_VEK, "vek_txt", "vek_kod", "vek", povinny=False, popis="věk")
    c_obd = najdi(df, COL_DOZITI_OBDOBI, "casref_do", "obdobi", "rok", povinny=False, popis="období")
    c_cis = next((c for c in df.columns if c.lower() in ("vuzemi_cis", "uzemi_cis")), None)
    c_kod = next((c for c in df.columns if c.lower() in ("vuzemi_kod", "uzemi_kod")), None)
    c_stapro = next((c for c in df.columns if c.lower() == "stapro_kod"), None)
    c_vekkod = next((c for c in df.columns if c.lower() == "vek_kod"), None)

    # Soubor od ČSÚ může obsahovat víc ukazatelů úmrtnostních tabulek; naděje dožití má kód 5411.
    if c_stapro and (df[c_stapro].astype(str).str.strip() == "5411").any():
        df = df[df[c_stapro].astype(str).str.strip() == "5411"]
        print("[dožití] ponechán ukazatel 5411 (naděje dožití)")

    # Soubor může obsahovat okresy i ORP. Okresů je v ČR 77, tak vybereme číselník, který jich má nejblíž.
    if c_cis and c_kod:
        pocty = df.groupby(c_cis)[c_kod].nunique()
        print(f"[dožití] počet oblastí podle číselníku: {pocty.to_dict()}")
        kandidati = pocty[(pocty >= 70) & (pocty <= 80)]
        if len(kandidati):
            vybrany = kandidati.index[0]
            df = df[df[c_cis] == vybrany]
            print(f"[dožití] použit číselník územních jednotek {vybrany} (okresy)")
        else:
            print("[dožití] POZOR: nenašel jsem číselník s ~77 oblastmi, beru všechny řádky.")

    # věk 0 = naděje dožití při narození (v číselníku ČSÚ má kód 400000600001000)
    if c_vekkod and (df[c_vekkod].astype(str).str.strip() == "400000600001000").any():
        df = df[df[c_vekkod].astype(str).str.strip() == "400000600001000"]
        print("[dožití] použit věk 0 (při narození)")
    elif c_vek:
        v = df[c_vek].astype(str).str.lower()
        maska = v.str.contains("narozen") | v.str.fullmatch(r"0+(\.0+)?") | v.str.startswith("0 ")
        if maska.any():
            df = df[maska]
        else:
            print(f"[dožití] POZOR: věk 0 jsem nenašel (hodnoty: {sorted(v.unique())[:8]}). Beru všechny věky!")

    # nejnovější období
    if c_obd:
        nejnovejsi = df[c_obd].astype(str).max()
        df = df[df[c_obd].astype(str) == nejnovejsi]
        obdobi = nejnovejsi
        print(f"[dožití] použito období: {obdobi}")
    else:
        obdobi = "neuvedeno"

    df = df.assign(_hod=cislo(df[c_hod]))
    p = df[c_poh].astype(str).str.lower()
    df["_poh"] = None
    df.loc[p.str.contains("muz|muž|^1$|^m$"), "_poh"] = "muzi"
    df.loc[p.str.contains("zen|žen|^2$|^z$"), "_poh"] = "zeny"
    df = df.dropna(subset=["_hod", "_poh"])
    df["_k"] = df[c_okr].map(klic)

    tab = df.pivot_table(index="_k", columns="_poh", values="_hod", aggfunc="mean")
    nazvy = df.drop_duplicates("_k").set_index("_k")[c_okr].map(lambda s: re.sub(r"^[Oo]kres\s+", "", str(s)))
    tab["okres"] = nazvy
    if "muzi" not in tab or "zeny" not in tab:
        konec("V datech o dožití chybí muži nebo ženy. Zkontrolujte sloupec s pohlavím.")
    tab = tab.dropna(subset=["muzi", "zeny"])
    print(f"[dožití] okresů s hodnotou: {len(tab)}")
    return tab, obdobi


# ------------------------------------------------------------------ kultura
def zpracuj_kulturu():
    soubory = sorted(glob.glob(os.path.join(D_KULTURA, "*.csv")))
    if not soubory:
        konec(f"Ve složce {D_KULTURA} není žádné CSV. Vložte tam aspoň jeden soubor (např. muzea.csv).")
    radky = []
    for f in soubory:
        typ = os.path.splitext(os.path.basename(f))[0].replace("_", " ")
        df = nacti_csv(f)
        c_okr = najdi(df, COL_KULTURA_OKRES, "okres", popis=f"okres v souboru {os.path.basename(f)}")
        c_kat = next((c for c in df.columns if bez_diakritiky(c).lower() == "kategorie"), None)
        print(f"[kultura] {os.path.basename(f)}: {len(df)} řádků, okres ve sloupci '{c_okr}'")
        if c_kat:
            vyl = [bez_diakritiky(v).lower() for v in VYLOUCIT_KATEGORIE]
            maska = df[c_kat].astype(str).map(lambda v: bez_diakritiky(v).lower()).isin(vyl)
            if maska.any():
                print(f"[kultura]   vyloučeno {int(maska.sum())} řádků s kategorií {VYLOUCIT_KATEGORIE}")
            df = df[~maska]
        chybi = int(df[c_okr].isna().sum())
        if chybi:
            print(f"[kultura]   {chybi} řádků bez okresu se přeskočí")
        vice = 0
        for okres, kat in zip(df[c_okr], df[c_kat] if c_kat else [None] * len(df)):
            if pd.isna(okres):
                continue
            casti = [c.strip() for c in str(okres).split(";") if c.strip()]
            vice += len(casti) > 1
            t = f"{typ}: {kat}" if c_kat and not pd.isna(kat) else typ
            for c in casti:             # památka ležící ve více okresech se počítá do každého z nich
                radky.append((klic(c), t))
        if vice:
            print(f"[kultura]   {vice} záznamů leží ve více okresech, počítají se do každého")
    k = pd.DataFrame(radky, columns=["_k", "typ"])
    return k


# ------------------------------------------------------------------ obyvatelé
def zpracuj_obyvatele():
    if not os.path.exists(F_OBYVATELE):
        print("[obyvatelé] soubor data/obyvatele.csv není, počítám jen absolutní počty.")
        return None
    df = nacti_csv(F_OBYVATELE)
    print(f"[obyvatelé] řádků: {len(df)}, sloupce: {list(df.columns)}")
    # V exportu ČSÚ jsou současně sloupce Stát, Region, Kraj a Okres.
    # Vybíráme explicitně sloupec Okres, nikoli první shodu s "ČR, regiony...".
    okresni_sloupce = [c for c in df.columns if bez_diakritiky(c).lower().endswith("-okres")]
    c_okr = COL_OBYV_OKRES or (okresni_sloupce[0] if okresni_sloupce else None)
    if c_okr is None:
        c_okr = najdi(df, None, "vuzemi_txt", "uzemi_txt", "okres", popis="území (obyvatelé)")
    elif c_okr not in df.columns:
        konec(f"Sloupec okresu '{c_okr}' v datech obyvatel neexistuje.")
    c_poc = najdi(df, COL_OBYV_POCET, "hodnota", "pocet", "obyvatel", popis="počet obyvatel")
    c_cis = next((c for c in df.columns if c.lower() in ("vuzemi_cis", "uzemi_cis")), None)
    c_poh = next((c for c in df.columns if c.lower() in ("pohlavi_txt", "pohlavi_kod")), None)
    c_obd = next((c for c in df.columns if c.lower() in ("casref_do", "rok", "roky")), None)
    c_stap = next((c for c in df.columns if c.lower() in ("stapro_kod", "ukazatel")), None)
    c_vek = next((c for c in df.columns if c.lower() in ("vek_txt", "vek_kod")), None)

    # soubor ČSÚ obsahuje všechna území (ČR, kraje, okresy, ORP, obce): necháme jen okresy (číselník 101)
    if c_cis:
        df = df[df[c_cis].astype(str).str.strip() == "101"]
    if c_vek and df[c_vek].nunique() > 1:
        print(f"[obyvatelé] POZOR: soubor obsahuje víc věkových skupin ({df[c_vek].nunique()}). "
              f"Použijte soubor 'Počet obyvatel podle pohlaví' (bez věku).")
    # nejnovější období
    if c_obd:
        nejnovejsi = df[c_obd].astype(str).max()
        df = df[df[c_obd].astype(str) == nejnovejsi]
        print(f"[obyvatelé] použito období: {nejnovejsi}")
    # více ukazatelů (stav k 1. 1., 1. 7., 31. 12.): přednost má stav k 31. 12.
    if c_stap and df[c_stap].nunique() > 1:
        kody = sorted(df[c_stap].astype(str).unique())
        vyber = next((k for k in kody if "31. 12" in k or "31.12" in k), kody[0])
        df = df[df[c_stap].astype(str) == vyber]
        print(f"[obyvatelé] více ukazatelů {kody}, použit '{vyber}'")
    # pohlaví: když jsou řádky zvlášť pro muže a ženy, sečteme je; celkový řádek (bez pohlaví) se nepřičítá dvakrát
    df = df.assign(_s="")
    if c_poh:
        t = df[c_poh].astype(str).str.lower()
        mz = df[t.str.contains("muž|muz|žen|zen|^1$|^2$")]
        if len(mz):
            df = mz.assign(_s=t[mz.index].str.slice(0, 1))
    # Praha je v tomto exportu vedena jako kraj, ale současně je okresem.
    # Doplníme ji z krajského řádku (jen Praha), ostatní krajské řádky ignorujeme.
    c_kraj = next((c for c in df.columns if bez_diakritiky(c).lower().endswith("-kraj")), None)
    if c_kraj:
        maska_praha = (df[c_okr].isna() &
                       df[c_kraj].astype(str).map(klic).eq("hlavni mesto praha"))
        df.loc[maska_praha, c_okr] = "Praha"
    df = df[df[c_okr].notna() & df[c_okr].astype(str).str.strip().ne("")].copy()
    # Preferujeme již agregované řádky "Celkem", a tedy nepřičítáme muže a ženy znovu.
    if c_poh and df[c_poh].astype(str).str.lower().eq("celkem").any():
        df = df[df[c_poh].astype(str).str.lower().eq("celkem")]
    df = df.assign(_k=df[c_okr].map(klic), _o=cislo(df[c_poc])).dropna(subset=["_o"])
    s = df.groupby("_k")["_o"].mean()
    print(f"[obyvatelé] sloupec s územím: '{c_okr}', počet různých území: {len(s)}")
    return s


def main():
    doz, obdobi = zpracuj_doziti()
    kult = zpracuj_kulturu()
    obyv = zpracuj_obyvatele()
    if obyv is not None:
        shoda = len(set(obyv.index) & set(doz.index))
        print(f"[obyvatelé] shoda s okresy z dožití: {shoda} z {len(doz)}")
        if shoda < 0.8 * len(doz):
            print("[obyvatelé] POZOR: soubor s obyvateli neobsahuje okresy (je asi jen za kraje). "
                  "Použiji absolutní počty. Stáhněte soubor znovu a zvolte území 'okresy'.")
            obyv = None

    typy = sorted(kult["typ"].unique())
    # pivot_table s values="typ" a columns="typ" vracel tabulku bez sloupců!
    # groupby.size počítá skutečný počet kulturních záznamů pro každý okres a typ.
    pocty = kult.groupby(["_k", "typ"]).size().unstack(fill_value=0)
    for t in typy:
        if t not in pocty:
            pocty[t] = 0

    nesedi = sorted(set(pocty.index) - set(doz.index))
    if nesedi:
        print(f"[spojení] POZOR: tyto okresy z kulturních dat nejsou v datech o dožití "
              f"(jiný název?): {nesedi[:10]}{' ...' if len(nesedi) > 10 else ''}")

    if JEN_OKRESY_S_KULTUROU:
        pred = len(doz)
        doz = doz[doz.index.isin(pocty.index)]
        print(f"[spojení] ponecháno {len(doz)} z {pred} okresů (jen ty, které mají kulturní data)")

    vysledek = []
    for k, r in doz.iterrows():
        typy_okresu = {t: int(pocty.loc[k, t]) if k in pocty.index else 0 for t in typy}
        celkem = sum(typy_okresu.values())
        o = float(obyv[k]) if obyv is not None and k in obyv.index else None
        vysledek.append({
            "okres": r["okres"],
            "muzi": round(float(r["muzi"]), 2),
            "zeny": round(float(r["zeny"]), 2),
            "kultura": celkem,
            "typy": typy_okresu,
            "obyvatele": o,
            "na10k": round(celkem / o * 10000, 2) if o else None,
        })
    if not any(v["kultura"] for v in vysledek):
        konec("Žádný okres z kulturních dat se nespároval s okresy z dožití. Podívejte se na názvy okresů v obou souborech.")

    meta = {
        "obdobi": obdobi,
        "typy": typy,
        "maPrepocet": obyv is not None and any(v["na10k"] is not None for v in vysledek),
        "pocetOkresu": len(vysledek),
    }
    with open(OUT, "w", encoding="utf-8") as f:
        f.write("window.DATA = " + json.dumps({"meta": meta, "okresy": vysledek}, ensure_ascii=False, indent=1) + ";\n")
    print(f"\nHotovo: {len(vysledek)} okresů zapsáno do {OUT}")
    print("Teď otevřete web/index.html v prohlížeči.")


if __name__ == "__main__":
    main()
