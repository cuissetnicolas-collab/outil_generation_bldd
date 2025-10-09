import pandas as pd
import numpy as np
from io import BytesIO
import streamlit as st
from datetime import datetime

# ========== Interface utilisateur ==========
st.title("📊 Générateur d'écritures analytiques - BLDD Edition")

# Fichier BLDD
fichier_entree = st.file_uploader("📂 Importer le fichier Excel BLDD", type=["xlsx"])

# Paramètres écriture
date_ecriture = st.date_input("📅 Date d'écriture")
journal = st.text_input("📒 Journal", value="VT")
libelle_base = st.text_input("📝 Libellé", value="VENTES BLDD")

# Comptes
compte_ca_brut = st.text_input("💰 Compte CA Brut", value="701100000")
compte_retour = st.text_input("💰 Compte Retours", value="709000000")
compte_remise = st.text_input("💰 Compte Remises libraires", value="709100000")
compte_tva = st.text_input("💰 Compte TVA collectée", value="445710060")
compte_tva_com = st.text_input("💰 Compte TVA déductible sur commissions", value="445660")
compte_com_dist = st.text_input("💰 Compte Commissions Distribution", value="622800000")
compte_com_diff = st.text_input("💰 Compte Commissions Diffusion", value="622800010")
compte_prov_retour_debit = st.text_input("💰 Compte Provisions retour (Débit)", value="681000000")
compte_prov_retour_credit = st.text_input("💰 Compte Provisions retour (Crédit)", value="151000000")

# Taux et montants
taux_diff = st.number_input("Taux diffusion (%)", value=9.0)/100
taux_dist = st.number_input("Taux distribution (%)", value=12.5)/100
taux_tva = 5.5/100
taux_tva_com = 5.5/100

# Montants fixes pour commissions et provisions
montant_com_dist_total = st.number_input("Montant total commissions distribution", value=1000.0, format="%.2f")
montant_com_diff_total = st.number_input("Montant total commissions diffusion", value=500.0, format="%.2f")
montant_prov_retour_reprise = st.number_input("Reprise ancienne provision 6 mois", value=0.0, format="%.2f")

if fichier_entree is not None:
    # ===== Lecture fichier BLDD =====
    df = pd.read_excel(fichier_entree, header=9, dtype={"ISBN": str})
    df.columns = df.columns.str.strip()
    df = df.dropna(subset=["ISBN"]).copy()

    df["ISBN"] = df["ISBN"].astype(str).str.strip().str.replace(r'\.0$', '', regex=True)
    df["ISBN"] = df["ISBN"].str.replace('-', '', regex=False).str.replace(' ', '', regex=False)

    # Conversion chiffres
    for c in ["Vente", "Retour", "Net", "Facture"]:
        df[c] = pd.to_numeric(df[c], errors="coerce").fillna(0).round(2)

    # ===== Commissions =====
    # Distribution
    raw_dist = df["Vente"] * taux_dist
    sum_raw_dist = raw_dist.sum()
    scaled_dist = raw_dist * (montant_com_dist_total / sum_raw_dist)
    cents_floor = np.floor(scaled_dist*100).astype(int)
    remainders = (scaled_dist*100) - cents_floor
    diff = int(round(montant_com_dist_total*100)) - cents_floor.sum()
    idx_sorted = np.argsort(-remainders.values)
    adjust = np.zeros(len(df), dtype=int)
    if diff > 0:
        adjust[idx_sorted[:diff]] = 1
    elif diff < 0:
        adjust[idx_sorted[len(df)+diff:]] = -1
    df["Commission_distribution"] = (cents_floor + adjust)/100.0

    # Diffusion
    raw_diff = df["Net"] * taux_diff
    sum_raw_diff = raw_diff.sum()
    scaled_diff = raw_diff * (montant_com_diff_total / sum_raw_diff)
    cents_floor = np.floor(scaled_diff*100).astype(int)
    remainders = (scaled_diff*100) - cents_floor
    diff = int(round(montant_com_diff_total*100)) - cents_floor.sum()
    idx_sorted = np.argsort(-remainders.values)
    adjust = np.zeros(len(df), dtype=int)
    if diff > 0:
        adjust[idx_sorted[:diff]] = 1
    elif diff < 0:
        adjust[idx_sorted[len(df)+diff:]] = -1
    df["Commission_diffusion"] = (cents_floor + adjust)/100.0

    # ===== Construction écritures =====
    ecritures = []

    # CA Brut (701)
    for _, r in df.iterrows():
        ecritures.append({
            "Date": date_ecriture.strftime("%d/%m/%Y"),
            "Journal": journal,
            "Compte": compte_ca_brut,
            "Libelle": f"{libelle_base} - CA Brut",
            "ISBN": r["ISBN"],
            "Débit": 0.0,
            "Crédit": r["Vente"]
        })

    # Retours (709) - en positif au débit
    for _, r in df.iterrows():
        ecritures.append({
            "Date": date_ecriture.strftime("%d/%m/%Y"),
            "Journal": journal,
            "Compte": compte_retour,
            "Libelle": f"{libelle_base} - Retours",
            "ISBN": r["ISBN"],
            "Débit": abs(r["Retour"]),
            "Crédit": 0.0
        })

    # Remises libraires (différence Net - Facture)
    df["Remises"] = (df["Net"] - df["Facture"]).round(2)
    for _, r in df.iterrows():
        ecritures.append({
            "Date": date_ecriture.strftime("%d/%m/%Y"),
            "Journal": journal,
            "Compte": compte_remise,
            "Libelle": f"{libelle_base} - Remises libraires",
            "ISBN": r["ISBN"],
            "Débit": r["Remises"],
            "Crédit": 0.0
        })

    # TVA collectée sur CA net après remises et retours
    df["CA_net_final"] = (df["Facture"] - df["Retour"]).clip(lower=0)
    tva_collectee = round(df["CA_net_final"].sum() * taux_tva, 2)
    ecritures.append({
        "Date": date_ecriture.strftime("%d/%m/%Y"),
        "Journal": journal,
        "Compte": compte_tva,
        "Libelle": f"{libelle_base} - TVA collectée",
        "ISBN": "",
        "Débit": 0.0,
        "Crédit": tva_collectee
    })

    # Commissions Distribution
    for _, r in df.iterrows():
        ecritures.append({
            "Date": date_ecriture.strftime("%d/%m/%Y"),
            "Journal": journal,
            "Compte": compte_com_dist,
            "Libelle": f"{libelle_base} - Com. Distribution",
            "ISBN": r["ISBN"],
            "Débit": r["Commission_distribution"],
            "Crédit": 0.0
        })

    # Commissions Diffusion
    for _, r in df.iterrows():
        ecritures.append({
            "Date": date_ecriture.strftime("%d/%m/%Y"),
            "Journal": journal,
            "Compte": compte_com_diff,
            "Libelle": f"{libelle_base} - Com. Diffusion",
            "ISBN": r["ISBN"],
            "Débit": r["Commission_diffusion"],
            "Crédit": 0.0
        })

    # TVA déductible sur commissions - ligne unique
    total_com = df["Commission_distribution"].sum() + df["Commission_diffusion"].sum()
    tva_com = round(total_com * taux_tva_com, 2)
    ecritures.append({
        "Date": date_ecriture.strftime("%d/%m/%Y"),
        "Journal": journal,
        "Compte": compte_tva_com,
        "Libelle": f"{libelle_base} - TVA sur commissions",
        "ISBN": "",
        "Débit": tva_com,
        "Crédit": 0.0
    })

    # Provisions pour retours
    prov_retour = round(df["Vente"].sum() * 1.055 * 0.10, 2)  # 10% TTC
    ecritures.append({
        "Date": date_ecriture.strftime("%d/%m/%Y"),
        "Journal": journal,
        "Compte": compte_prov_retour_debit,
        "Libelle": f"{libelle_base} - Provision retours",
        "ISBN": "",
        "Débit": prov_retour,
        "Crédit": 0.0
    })
    ecritures.append({
        "Date": date_ecriture.strftime("%d/%m/%Y"),
        "Journal": journal,
        "Compte": compte_prov_retour_credit,
        "Libelle": f"{libelle_base} - Provision retours",
        "ISBN": "",
        "Débit": 0.0,
        "Crédit": prov_retour
    })

    # Reprise ancienne provision
    if montant_prov_retour_reprise != 0.0:
        ecritures.append({
            "Date": date_ecriture.strftime("%d/%m/%Y"),
            "Journal": journal,
            "Compte": compte_prov_retour_debit,
            "Libelle": f"{libelle_base} - Reprise ancienne provision",
            "ISBN": "",
            "Débit": 0.0,
            "Crédit": montant_prov_retour_reprise
        })
        ecritures.append({
            "Date": date_ecriture.strftime("%d/%m/%Y"),
            "Journal": journal,
            "Compte": compte_prov_retour_credit,
            "Libelle": f"{libelle_base} - Reprise ancienne provision",
            "ISBN": "",
            "Débit": montant_prov_retour_reprise,
            "Crédit": 0.0
        })

    # ===== Création DataFrame final =====
    df_ecr = pd.DataFrame(ecritures)

    # Vérification équilibre
    total_debit = round(df_ecr["Débit"].sum(), 2)
    total_credit = round(df_ecr["Crédit"].sum(), 2)
    if total_debit != total_credit:
        st.error(f"⚠️ Écriture déséquilibrée : Débit={total_debit}, Crédit={total_credit}")
    else:
        st.success("✅ Écritures équilibrées !")

    # Export Excel
    buffer = BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        df_ecr.to_excel(writer, index=False, sheet_name="Ecritures")
    buffer.seek(0)
    st.download_button(
        label="📥 Télécharger les écritures (Excel)",
        data=buffer,
        file_name="Ecritures_BLDD.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )

    # Aperçu
    st.subheader("👀 Aperçu des écritures générées")
    st.dataframe(df_ecr)
