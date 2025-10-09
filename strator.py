import pandas as pd
import numpy as np
from io import BytesIO
import streamlit as st
from datetime import date

# ========== Interface utilisateur ==========
st.title("📊 BLDD Edition - Générateur d'écritures analytiques")

# Import fichier BLDD
fichier_entree = st.file_uploader("📂 Importer le fichier Excel BLDD", type=["xlsx"])
date_ecriture = st.date_input("📅 Date d'écriture", value=date.today())
journal = st.text_input("📒 Journal", value="VT")
libelle_base = st.text_input("📝 Libellé", value="VENTES BLDD")

# Comptes
compte_ca = st.text_input("💰 Compte CA Brut", value="701100000")
compte_retour = st.text_input("💰 Compte Retours", value="709000000")
compte_remise = st.text_input("💰 Compte Remises libraires", value="709100000")
compte_com_dist = st.text_input("💰 Compte Commissions distribution", value="622800000")
compte_com_diff = st.text_input("💰 Compte Commissions diffusion", value="622800010")
compte_tva_coll = st.text_input("💰 Compte TVA collectée", value="445710060")
compte_tva_ded = st.text_input("💰 Compte TVA déductible", value="445660")
compte_prov_ret = st.text_input("💰 Compte Provision retours (Débit)", value="681000000")
compte_prov_ret_credit = st.text_input("💰 Compte Provision retours (Crédit)", value="151000000")

# Taux
taux_tva = st.number_input("TVA (%)", value=5.5)/100
taux_dist = st.number_input("Taux distribution (%)", value=12.5)/100
taux_diff = st.number_input("Taux diffusion (%)", value=9.0)/100

# Montants commissions totaux
com_distribution_total = st.number_input("Montant total commissions distribution", value=1000.0, format="%.2f")
com_diffusion_total = st.number_input("Montant total commissions diffusion", value=500.0, format="%.2f")

# Provisions anciennes
prov_ancienne = st.number_input("Montant reprise ancienne provision", value=0.0, format="%.2f")

# ========== Traitement ==========
if fichier_entree is not None:
    # Lecture fichier
    df = pd.read_excel(fichier_entree, header=9, dtype={"ISBN": str})
    df.columns = df.columns.str.strip()
    df = df.dropna(subset=["ISBN"]).copy()
    
    # Nettoyage ISBN
    df["ISBN"] = df["ISBN"].astype(str).str.strip().str.replace(r'\.0$', '', regex=True)
    df["ISBN"] = df["ISBN"].str.replace('-', '', regex=False).str.replace(' ', '', regex=False)
    
    for c in ["Vente","Retour","Net","Facture"]:
        df[c] = pd.to_numeric(df[c], errors="coerce").fillna(0).round(2)

    # Remises libraires
    df["Remise"] = (df["Net"] - df["Facture"]).round(2)
    
    # Ajuster retours en positif
    df["Retour"] = df["Retour"].abs()
    
    # Commissions distribution
    raw_dist = df["Net"] * taux_dist
    sum_raw_dist = raw_dist.sum()
    scaled_dist = raw_dist * (com_distribution_total / sum_raw_dist)
    cents_floor = np.floor(scaled_dist * 100).astype(int)
    remainders = (scaled_dist*100) - cents_floor
    diff = int(round(com_distribution_total*100)) - cents_floor.sum()
    idx_sorted = np.argsort(-remainders.values)
    adjust = np.zeros(len(df), dtype=int)
    if diff>0:
        adjust[idx_sorted[:diff]] = 1
    elif diff<0:
        adjust[idx_sorted[len(df)+diff:]] = -1
    df["Com_dist"] = (cents_floor + adjust)/100.0

    # Commissions diffusion
    raw_diff = df["Net"] * taux_diff
    sum_raw_diff = raw_diff.sum()
    scaled_diff = raw_diff * (com_diffusion_total / sum_raw_diff)
    cents_floor = np.floor(scaled_diff*100).astype(int)
    remainders = (scaled_diff*100) - cents_floor
    diff = int(round(com_diffusion_total*100)) - cents_floor.sum()
    idx_sorted = np.argsort(-remainders.values)
    adjust = np.zeros(len(df), dtype=int)
    if diff>0:
        adjust[idx_sorted[:diff]] = 1
    elif diff<0:
        adjust[idx_sorted[len(df)+diff:]] = -1
    df["Com_diff"] = (cents_floor + adjust)/100.0

    # ========== Construction écritures ==========
    ecritures = []

    # CA brut
    for _, r in df.iterrows():
        if r["Vente"] !=0:
            ecritures.append({
                "Date": date_ecriture.strftime("%d/%m/%Y"), "Journal": journal, "Compte": compte_ca,
                "Libelle": f"{libelle_base} - CA Brut", "ISBN": r["ISBN"],
                "Débit": 0.0, "Crédit": r["Vente"]
            })
    # Retours
    for _, r in df.iterrows():
        if r["Retour"] !=0:
            ecritures.append({
                "Date": date_ecriture.strftime("%d/%m/%Y"), "Journal": journal, "Compte": compte_retour,
                "Libelle": f"{libelle_base} - Retours", "ISBN": r["ISBN"],
                "Débit": r["Retour"], "Crédit": 0.0
            })
    # Remises libraires
    for _, r in df.iterrows():
        if r["Remise"] !=0:
            ecritures.append({
                "Date": date_ecriture.strftime("%d/%m/%Y"), "Journal": journal, "Compte": compte_remise,
                "Libelle": f"{libelle_base} - Remises libraires", "ISBN": r["ISBN"],
                "Débit": r["Remise"], "Crédit": 0.0
            })

    # Commissions distribution
    for _, r in df.iterrows():
        if r["Com_dist"] !=0:
            ecritures.append({
                "Date": date_ecriture.strftime("%d/%m/%Y"), "Journal": journal, "Compte": compte_com_dist,
                "Libelle": f"{libelle_base} - Commissions distribution", "ISBN": r["ISBN"],
                "Débit": r["Com_dist"], "Crédit": 0.0
            })
    # Commissions diffusion
    for _, r in df.iterrows():
        if r["Com_diff"] !=0:
            ecritures.append({
                "Date": date_ecriture.strftime("%d/%m/%Y"), "Journal": journal, "Compte": compte_com_diff,
                "Libelle": f"{libelle_base} - Commissions diffusion", "ISBN": r["ISBN"],
                "Débit": r["Com_diff"], "Crédit": 0.0
            })

    # TVA collectée sur CA net après remise et retours
    ca_net = (df["Net"] - df["Remise"] - df["Retour"]).sum().round(2)
    tva_coll = round(ca_net * taux_tva,2)
    ecritures.append({
        "Date": date_ecriture.strftime("%d/%m/%Y"), "Journal": journal, "Compte": compte_tva_coll,
        "Libelle": f"{libelle_base} - TVA collectée", "ISBN": "",
        "Débit": 0.0, "Crédit": tva_coll
    })

    # TVA déductible sur commissions
    tva_ded = round((df["Com_dist"].sum() + df["Com_diff"].sum()) * taux_tva,2)
    ecritures.append({
        "Date": date_ecriture.strftime("%d/%m/%Y"), "Journal": journal, "Compte": compte_tva_ded,
        "Libelle": f"{libelle_base} - TVA déductible sur commissions", "ISBN": "",
        "Débit": tva_ded, "Crédit": 0.0
    })

    # Provision retours
    prov_ret = round(df["Vente"].sum()*1.055*0.10,2)  # 10% TTC sur CA brut
    ecritures.append({
        "Date": date_ecriture.strftime("%d/%m/%Y"), "Journal": journal, "Compte": compte_prov_ret,
        "Libelle": f"{libelle_base} - Provision retours", "ISBN": "",
        "Débit": prov_ret, "Crédit": 0.0
    })
    if prov_ancienne>0:
        ecritures.append({
            "Date": date_ecriture.strftime("%d/%m/%Y"), "Journal": journal, "Compte": compte_prov_ret_credit,
            "Libelle": f"{libelle_base} - Reprise ancienne provision", "ISBN": "",
            "Débit": 0.0, "Crédit": prov_ancienne
        })

    # ========== Export & affichage ==========
    df_ecr = pd.DataFrame(ecritures)

    # Vérification équilibre
    total_debit = round(df_ecr["Débit"].sum(),2)
    total_credit = round(df_ecr["Crédit"].sum(),2)
    if total_debit != total_credit:
        st.error(f"⚠️ Écritures déséquilibrées : Débit={total_debit}, Crédit={total_credit}")
    else:
        st.success("✅ Écritures équilibrées !")

    # Aperçu
    st.subheader("👀 Aperçu des écritures générées")
    st.dataframe(df_ecr)

    # Export Excel
    buffer = BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        df_ecr.to_excel(writer, index=False, sheet_name="Ecritures")
    buffer.seek(0)
    st.download_button("📥 Télécharger les écritures (Excel)", data=buffer,
                       file_name="Ecritures_BLDD.xlsx",
                       mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
