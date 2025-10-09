import pandas as pd
import numpy as np
from io import BytesIO
import streamlit as st
from datetime import date

# ========== Interface utilisateur ==========
st.title("📊 Générateur d'écritures analytiques - BLDD")

fichier_entree = st.file_uploader("📂 Importer le fichier Excel BLDD", type=["xlsx"])
date_ecriture = st.date_input("📅 Date d'écriture", value=date.today())
journal = st.text_input("📒 Journal", value="VT")
libelle_base = st.text_input("📝 Libellé", value="VENTES BLDD")

# Comptes
compte_ca = "701100000"
compte_retour = "709000000"
compte_remise = "709100000"
compte_tva = "445710060"
compte_com_dist = "622800000"
compte_com_diff = "622800010"
compte_tva_com = "445660000"
compte_provision = "681000000"
compte_reprise = "151000000"

# 🔹 Taux
taux_tva = 0.055
taux_com_dist = st.number_input("Taux distribution (%)", value=12.5)/100
taux_com_diff = st.number_input("Taux diffusion (%)", value=9.0)/100

# 🔹 Montants totaux commissions et reprise provision
com_dist_total = st.number_input("Montant total commissions distribution", value=1000.0, format="%.2f")
com_diff_total = st.number_input("Montant total commissions diffusion", value=500.0, format="%.2f")
provision_reprise = st.number_input("Montant reprise ancienne provision (6 mois)", value=0.0, format="%.2f")

if fichier_entree is not None:
    df = pd.read_excel(fichier_entree, header=9, dtype={"ISBN": str})
    df.columns = df.columns.str.strip()
    df = df.dropna(subset=["ISBN"]).copy()

    # Nettoyage ISBN
    df["ISBN"] = df["ISBN"].astype(str).str.strip().str.replace(r'\.0$', '', regex=True)
    df["ISBN"] = df["ISBN"].str.replace('-', '', regex=False).str.replace(' ', '', regex=False)

    # Colonnes numériques
    for c in ["Vente", "Retour", "Net", "Facture"]:
        df[c] = pd.to_numeric(df[c], errors="coerce").fillna(0).round(2)

    # 🔹 Calcul des remises libraires
    df["Remise_libraire"] = (df["Net"] - df["Facture"]).round(2)

    # 🔹 Commissions distribution
    raw_dist = df["Vente"] * taux_com_dist
    sum_raw_dist = raw_dist.sum()
    scaled_dist = raw_dist * (com_dist_total / sum_raw_dist)
    cents_floor = np.floor(scaled_dist * 100).astype(int)
    remainders = (scaled_dist * 100) - cents_floor
    target_cents = int(round(com_dist_total * 100))
    diff = target_cents - cents_floor.sum()
    idx_sorted = np.argsort(-remainders.values)
    adjust = np.zeros(len(df), dtype=int)
    if diff > 0:
        adjust[idx_sorted[:diff]] = 1
    elif diff < 0:
        adjust[idx_sorted[len(df)+diff:]] = -1
    df["Com_dist"] = (cents_floor + adjust)/100.0

    # 🔹 Commissions diffusion
    raw_diff = df["Net"] * taux_com_diff
    sum_raw_diff = raw_diff.sum()
    scaled_diff = raw_diff * (com_diff_total / sum_raw_diff)
    cents_floor = np.floor(scaled_diff * 100).astype(int)
    remainders = (scaled_diff * 100) - cents_floor
    target_cents = int(round(com_diff_total * 100))
    diff = target_cents - cents_floor.sum()
    idx_sorted = np.argsort(-remainders.values)
    adjust = np.zeros(len(df), dtype=int)
    if diff > 0:
        adjust[idx_sorted[:diff]] = 1
    elif diff < 0:
        adjust[idx_sorted[len(df)+diff:]] = -1
    df["Com_diff"] = (cents_floor + adjust)/100.0

    # 🔹 Provisions retours (10% TTC sur CA brut)
    df["Provision_retour"] = (df["Vente"] * 1.055 * 0.10).round(2)  # TTC approximatif

    # ========== Construction des écritures ==========
    ecritures = []

    for _, r in df.iterrows():
        # CA brut
        ecritures.append({
            "Date": date_ecriture.strftime("%d/%m/%Y"),
            "Journal": journal,
            "Compte": compte_ca,
            "Libelle": f"{libelle_base} - CA brut",
            "ISBN": r["ISBN"],
            "Débit": 0.0,
            "Crédit": r["Vente"]
        })
        # Retours
        ecritures.append({
            "Date": date_ecriture.strftime("%d/%m/%Y"),
            "Journal": journal,
            "Compte": compte_retour,
            "Libelle": f"{libelle_base} - Retour",
            "ISBN": r["ISBN"],
            "Débit": r["Retour"],
            "Crédit": 0.0
        })
        # Remises libraires
        ecritures.append({
            "Date": date_ecriture.strftime("%d/%m/%Y"),
            "Journal": journal,
            "Compte": compte_remise,
            "Libelle": f"{libelle_base} - Remise libraire",
            "ISBN": r["ISBN"],
            "Débit": r["Remise_libraire"],
            "Crédit": 0.0
        })
        # Commissions distribution
        ecritures.append({
            "Date": date_ecriture.strftime("%d/%m/%Y"),
            "Journal": journal,
            "Compte": compte_com_dist,
            "Libelle": f"{libelle_base} - Com. distribution",
            "ISBN": r["ISBN"],
            "Débit": r["Com_dist"],
            "Crédit": 0.0
        })
        # Commissions diffusion
        ecritures.append({
            "Date": date_ecriture.strftime("%d/%m/%Y"),
            "Journal": journal,
            "Compte": compte_com_diff,
            "Libelle": f"{libelle_base} - Com. diffusion",
            "ISBN": r["ISBN"],
            "Débit": r["Com_diff"],
            "Crédit": 0.0
        })

    # TVA collectée (5,5% sur Net - remises et retours)
    total_tva = ((df["Net"] - df["Remise_libraire"] - df["Retour"]) * taux_tva).sum().round(2)
    ecritures.append({
        "Date": date_ecriture.strftime("%d/%m/%Y"),
        "Journal": journal,
        "Compte": compte_tva,
        "Libelle": f"{libelle_base} - TVA collectée",
        "ISBN": "",
        "Débit": 0.0,
        "Crédit": total_tva
    })

    # TVA sur commissions
    tva_com = ((df["Com_dist"] + df["Com_diff"]) * taux_tva).sum().round(2)
    ecritures.append({
        "Date": date_ecriture.strftime("%d/%m/%Y"),
        "Journal": journal,
        "Compte": compte_tva_com,
        "Libelle": f"{libelle_base} - TVA sur commissions",
        "ISBN": "",
        "Débit": 0.0,
        "Crédit": tva_com
    })

    # Provisions retours
    prov_total = df["Provision_retour"].sum().round(2)
    ecritures.append({
        "Date": date_ecriture.strftime("%d/%m/%Y"),
        "Journal": journal,
        "Compte": compte_provision,
        "Libelle": f"{libelle_base} - Provision retours",
        "ISBN": "",
        "Débit": prov_total,
        "Crédit": 0.0
    })

    # Reprise ancienne provision
    ecritures.append({
        "Date": date_ecriture.strftime("%d/%m/%Y"),
        "Journal": journal,
        "Compte": compte_reprise,
        "Libelle": f"{libelle_base} - Reprise ancienne provision",
        "ISBN": "",
        "Débit": 0.0,
        "Crédit": provision_reprise
    })

    df_ecr = pd.DataFrame(ecritures)

    # Vérification équilibre
    total_debit = df_ecr["Débit"].sum().round(2)
    total_credit = df_ecr["Crédit"].sum().round(2)
    if total_debit != total_credit:
        st.warning(f"⚠️ Écriture déséquilibrée : Débit={total_debit}, Crédit={total_credit}")
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

    st.subheader("👀 Aperçu des écritures générées")
    st.dataframe(df_ecr)
