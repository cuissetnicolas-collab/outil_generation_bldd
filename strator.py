import streamlit as st
import pandas as pd
import numpy as np
from io import BytesIO

st.title("📊 Générateur d'écritures analytiques - BLDD (Edition Comptable)")

# =====================
# Import du fichier BLDD
# =====================
fichier_entree = st.file_uploader("📂 Importer le fichier Excel BLDD", type=["xlsx"])
date_ecriture = st.date_input("📅 Date d'écriture")
journal = st.text_input("📒 Journal", value="VT")
libelle_base = st.text_input("📝 Libellé", value="VENTES BLDD")

# Comptes
compte_ca_brut = st.text_input("💰 Compte CA Brut (701)", value="70110000")
compte_retour = st.text_input("💰 Compte Retours (709)", value="70910000")
compte_ca_net = st.text_input("💰 Compte CA Net (701)", value="70110100")
compte_com_dist = st.text_input("💰 Compte Commissions Distribution", value="62280000")
compte_com_diff = st.text_input("💰 Compte Commissions Diffusion", value="62280001")
compte_prov_retour = st.text_input("💰 Compte Provision Retours", value="41910000")
compte_tva = st.text_input("💰 Compte TVA collectée", value="44570000")

# Taux et montants
taux_dist = st.number_input("Taux distribution (%)", value=12.5)/100
taux_diff = st.number_input("Taux diffusion (%)", value=9.0)/100
taux_provision_retour = st.number_input("Provision retours (%)", value=10.0)/100
taux_tva = st.number_input("TVA (%)", value=5.5)/100  # à ajuster selon produit

if fichier_entree is not None:
    df = pd.read_excel(fichier_entree, header=9, dtype={"ISBN": str})
    df.columns = df.columns.str.strip()
    df = df.dropna(subset=["ISBN"]).copy()
    
    df["ISBN"] = df["ISBN"].astype(str).str.strip().str.replace(r'\.0$', '', regex=True)
    df["ISBN"] = df["ISBN"].str.replace('-', '', regex=False).str.replace(' ', '', regex=False)
    
    for c in ["Vente", "Retour", "Net", "Facture"]:
        df[c] = pd.to_numeric(df[c], errors="coerce").fillna(0).round(2)

    # =====================
    # Calcul commissions distribution et diffusion
    # =====================
    # Distribution
    raw_dist = df["Net"] * taux_dist
    sum_raw_dist = raw_dist.sum()
    com_distribution_total = raw_dist.sum()
    scaled_dist = raw_dist * (com_distribution_total / sum_raw_dist)
    cents_floor = np.floor(scaled_dist*100).astype(int)
    remainders = (scaled_dist*100) - cents_floor
    target_cents = int(round(com_distribution_total*100))
    diff = target_cents - cents_floor.sum()
    idx_sorted = np.argsort(-remainders.values)
    adjust = np.zeros(len(df), dtype=int)
    if diff > 0:
        adjust[idx_sorted[:diff]] = 1
    elif diff < 0:
        adjust[idx_sorted[len(df)+diff:]] = -1
    df["Commission_distribution"] = (cents_floor+adjust)/100.0

    # Diffusion
    raw_diff = df["Net"] * taux_diff
    sum_raw_diff = raw_diff.sum()
    com_diffusion_total = raw_diff.sum()
    scaled_diff = raw_diff * (com_diffusion_total / sum_raw_diff)
    cents_floor = np.floor(scaled_diff*100).astype(int)
    remainders = (scaled_diff*100) - cents_floor
    target_cents = int(round(com_diffusion_total*100))
    diff = target_cents - cents_floor.sum()
    idx_sorted = np.argsort(-remainders.values)
    adjust = np.zeros(len(df), dtype=int)
    if diff > 0:
        adjust[idx_sorted[:diff]] = 1
    elif diff < 0:
        adjust[idx_sorted[len(df)+diff:]] = -1
    df["Commission_diffusion"] = (cents_floor+adjust)/100.0

    # =====================
    # Construction écritures analytiques
    # =====================
    ecritures = []

    # CA brut
    ecritures.append({
        "Date": date_ecriture.strftime("%d/%m/%Y"),
        "Journal": journal,
        "Compte": compte_ca_brut,
        "Libelle": f"{libelle_base} - CA brut global",
        "ISBN": "",
        "Débit": 0.0,
        "Crédit": df["Vente"].sum()
    })
    for _, r in df.iterrows():
        ecritures.append({
            "Date": date_ecriture.strftime("%d/%m/%Y"),
            "Journal": journal,
            "Compte": compte_ca_brut,
            "Libelle": f"{libelle_base} - CA brut ISBN",
            "ISBN": r["ISBN"],
            "Débit": 0.0,
            "Crédit": r["Vente"]
        })

    # Retours
    ecritures.append({
        "Date": date_ecriture.strftime("%d/%m/%Y"),
        "Journal": journal,
        "Compte": compte_retour,
        "Libelle": f"{libelle_base} - Retours global",
        "ISBN": "",
        "Débit": df["Retour"].sum(),
        "Crédit": 0.0
    })
    for _, r in df.iterrows():
        ecritures.append({
            "Date": date_ecriture.strftime("%d/%m/%Y"),
            "Journal": journal,
            "Compte": compte_retour,
            "Libelle": f"{libelle_base} - Retours ISBN",
            "ISBN": r["ISBN"],
            "Débit": r["Retour"],
            "Crédit": 0.0
        })

    # CA net après remise
    ecritures.append({
        "Date": date_ecriture.strftime("%d/%m/%Y"),
        "Journal": journal,
        "Compte": compte_ca_net,
        "Libelle": f"{libelle_base} - CA net global",
        "ISBN": "",
        "Débit": 0.0,
        "Crédit": df["Facture"].sum()
    })
    for _, r in df.iterrows():
        ecritures.append({
            "Date": date_ecriture.strftime("%d/%m/%Y"),
            "Journal": journal,
            "Compte": compte_ca_net,
            "Libelle": f"{libelle_base} - CA net ISBN",
            "ISBN": r["ISBN"],
            "Débit": 0.0,
            "Crédit": r["Facture"]
        })

    # Provision retours (10% TTC sur CA brut)
    montant_prov = df["Vente"].sum()*(1+taux_tva)*taux_provision_retour
    ecritures.append({
        "Date": date_ecriture.strftime("%d/%m/%Y"),
        "Journal": journal,
        "Compte": compte_prov_retour,
        "Libelle": f"{libelle_base} - Provision retours",
        "ISBN": "",
        "Débit": 0.0,
        "Crédit": montant_prov
    })

    # Commissions distribution et diffusion
    total_dist = df["Commission_distribution"].sum()
    total_diff = df["Commission_diffusion"].sum()

    ecritures.append({
        "Date": date_ecriture.strftime("%d/%m/%Y"),
        "Journal": journal,
        "Compte": compte_com_dist,
        "Libelle": f"{libelle_base} - Commissions distribution",
        "ISBN": "",
        "Débit": total_dist,
        "Crédit": 0.0
    })
    ecritures.append({
        "Date": date_ecriture.strftime("%d/%m/%Y"),
        "Journal": journal,
        "Compte": compte_com_diff,
        "Libelle": f"{libelle_base} - Commissions diffusion",
        "ISBN": "",
        "Débit": total_diff,
        "Crédit": 0.0
    })

    # =====================
    # Création dataframe
    # =====================
    df_ecr = pd.DataFrame(ecritures)

    # Vérification équilibre
    total_debit = df_ecr["Débit"].sum()
    total_credit = df_ecr["Crédit"].sum()
    if round(total_debit,2) != round(total_credit,2):
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

    st.subheader("👀 Aperçu des écritures générées")
    st.dataframe(df_ecr)
