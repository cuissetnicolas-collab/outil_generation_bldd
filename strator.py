import pandas as pd
import numpy as np
from io import BytesIO
import streamlit as st

# ================= Interface utilisateur =================
st.title("📊 Générateur d'écritures analytiques - BLDD")

# Import fichier BLDD
fichier_entree = st.file_uploader("📂 Importer le fichier Excel BLDD", type=["xlsx"])
date_ecriture = st.date_input("📅 Date d'écriture")
journal = st.text_input("📒 Journal", value="VT")
libelle_base = st.text_input("📝 Libellé", value="VENTES BLDD")

# Comptes
compte_ca_brut = st.text_input("💰 Compte CA Brut (701)", value="701100000")
compte_retour = st.text_input("💰 Compte Retours (709000000)", value="709000000")
compte_remise = st.text_input("💰 Compte Remises libraires (709100000)", value="709100000")
compte_tva_vente = st.text_input("💰 Compte TVA vente (445710060)", value="445710060")
compte_com_dist = st.text_input("💰 Compte commissions distribution (622800000)", value="622800000")
compte_com_diff = st.text_input("💰 Compte commissions diffusion (622800010)", value="622800010")
compte_tva_commission = st.text_input("💰 Compte TVA déductible sur commissions (445660)", value="445660")
compte_prov_debit = st.text_input("💰 Compte provision retours (681)", value="681000000")
compte_prov_credit = st.text_input("💰 Compte provision retours (151)", value="151000000")

# Taux et montants
taux_tva = st.number_input("Taux TVA (%)", value=5.5) / 100
taux_prov = st.number_input("Taux provision retours (%)", value=10.0) / 100

montant_com_dist_total = st.number_input("Montant total commissions distribution", value=1000.0, format="%.2f")
montant_com_diff_total = st.number_input("Montant total commissions diffusion", value=500.0, format="%.2f")
montant_reprise_prov = st.number_input("Reprise provision ancienne (si applicable)", value=0.0, format="%.2f")

# ================= Traitement =================
if fichier_entree is not None:
    df = pd.read_excel(fichier_entree, header=9, dtype={"ISBN": str})
    df.columns = df.columns.str.strip()
    df = df.dropna(subset=["ISBN"]).copy()

    # Nettoyage ISBN
    df["ISBN"] = df["ISBN"].astype(str).str.strip().str.replace(r'\.0$', '', regex=True)
    df["ISBN"] = df["ISBN"].str.replace('-', '', regex=False).str.replace(' ', '', regex=False)

    # Colonnes financières
    for c in ["Vente", "Retour", "Net", "Facture"]:
        df[c] = pd.to_numeric(df[c], errors="coerce").fillna(0).round(2)

    # ================= Commissions =================
    # Distribution
    raw_dist = df["Vente"] * (1.0)  # proportionnel
    sum_raw_dist = raw_dist.sum()
    scaled_dist = raw_dist * (montant_com_dist_total / sum_raw_dist)
    cents_floor = np.floor(scaled_dist * 100).astype(int)
    remainders = (scaled_dist * 100) - cents_floor
    diff = int(round(montant_com_dist_total * 100)) - cents_floor.sum()
    idx_sorted = np.argsort(-remainders.values)
    adjust = np.zeros(len(df), dtype=int)
    if diff > 0:
        adjust[idx_sorted[:diff]] = 1
    elif diff < 0:
        adjust[idx_sorted[len(df)+diff:]] = -1
    df["Commission_distribution"] = (cents_floor + adjust) / 100.0

    # Diffusion
    raw_diff = df["Net"] * (1.0)
    sum_raw_diff = raw_diff.sum()
    scaled_diff = raw_diff * (montant_com_diff_total / sum_raw_diff)
    cents_floor = np.floor(scaled_diff * 100).astype(int)
    remainders = (scaled_diff * 100) - cents_floor
    diff = int(round(montant_com_diff_total * 100)) - cents_floor.sum()
    idx_sorted = np.argsort(-remainders.values)
    adjust = np.zeros(len(df), dtype=int)
    if diff > 0:
        adjust[idx_sorted[:diff]] = 1
    elif diff < 0:
        adjust[idx_sorted[len(df)+diff:]] = -1
    df["Commission_diffusion"] = (cents_floor + adjust) / 100.0

    # ================= Construction écritures =================
    ecritures = []

    # Ventes brutes (701)
    for _, r in df.iterrows():
        ecritures.append({
            "Date": date_ecriture.strftime("%d/%m/%Y"),
            "Journal": journal,
            "Compte": compte_ca_brut,
            "Libelle": f"{libelle_base} - CA Brut",
            "Analytique": r["ISBN"],
            "Débit": 0.0,
            "Crédit": r["Vente"]
        })

    # Retours (709)
    for _, r in df.iterrows():
        ecritures.append({
            "Date": date_ecriture.strftime("%d/%m/%Y"),
            "Journal": journal,
            "Compte": compte_retour,
            "Libelle": f"{libelle_base} - Retours",
            "Analytique": r["ISBN"],
            "Débit": r["Retour"],
            "Crédit": 0.0
        })

    # Remises libraires (7091)
    df["Remise"] = df["Net"] - df["Facture"]
    for _, r in df.iterrows():
        if r["Remise"] != 0:
            ecritures.append({
                "Date": date_ecriture.strftime("%d/%m/%Y"),
                "Journal": journal,
                "Compte": compte_remise,
                "Libelle": f"{libelle_base} - Remises",
                "Analytique": r["ISBN"],
                "Débit": r["Remise"],
                "Crédit": 0.0
            })

    # TVA sur ventes nettes après remises et retours
    df["CA_net_ajuste"] = df["Facture"] - df["Retour"]
    tva_vente = round(df["CA_net_ajuste"].sum() * taux_tva, 2)
    ecritures.append({
        "Date": date_ecriture.strftime("%d/%m/%Y"),
        "Journal": journal,
        "Compte": compte_tva_vente,
        "Libelle": f"{libelle_base} - TVA vente 5,5%",
        "Analytique": "",
        "Débit": 0.0,
        "Crédit": tva_vente
    })

    # Commissions distribution et diffusion
    for _, r in df.iterrows():
        # Distribution
        ecritures.append({
            "Date": date_ecriture.strftime("%d/%m/%Y"),
            "Journal": journal,
            "Compte": compte_com_dist,
            "Libelle": f"{libelle_base} - Com distribution",
            "Analytique": r["ISBN"],
            "Débit": r["Commission_distribution"],
            "Crédit": 0.0
        })
        # Diffusion
        ecritures.append({
            "Date": date_ecriture.strftime("%d/%m/%Y"),
            "Journal": journal,
            "Compte": compte_com_diff,
            "Libelle": f"{libelle_base} - Com diffusion",
            "Analytique": r["ISBN"],
            "Débit": r["Commission_diffusion"],
            "Crédit": 0.0
        })

    # TVA déductible sur commissions
    tva_com_dist = round(df["Commission_distribution"].sum() * taux_tva, 2)
    tva_com_diff = round(df["Commission_diffusion"].sum() * taux_tva, 2)
    if tva_com_dist > 0:
        ecritures.append({
            "Date": date_ecriture.strftime("%d/%m/%Y"),
            "Journal": journal,
            "Compte": compte_tva_commission,
            "Libelle": f"{libelle_base} - TVA déductible Com dist",
            "Analytique": "",
            "Débit": tva_com_dist,
            "Crédit": 0.0
        })
    if tva_com_diff > 0:
        ecritures.append({
            "Date": date_ecriture.strftime("%d/%m/%Y"),
            "Journal": journal,
            "Compte": compte_tva_commission,
            "Libelle": f"{libelle_base} - TVA déductible Com diff",
            "Analytique": "",
            "Débit": tva_com_diff,
            "Crédit": 0.0
        })

    # Provisions pour retours
    prov_montant = round(df["Vente"].sum() * taux_prov, 2)
    if prov_montant > 0:
        ecritures.append({
            "Date": date_ecriture.strftime("%d/%m/%Y"),
            "Journal": journal,
            "Compte": compte_prov_debit,
            "Libelle": f"{libelle_base} - Provision retours",
            "Analytique": "",
            "Débit": prov_montant,
            "Crédit": 0.0
        })
        ecritures.append({
            "Date": date_ecriture.strftime("%d/%m/%Y"),
            "Journal": journal,
            "Compte": compte_prov_credit,
            "Libelle": f"{libelle_base} - Provision retours",
            "Analytique": "",
            "Débit": 0.0,
            "Crédit": prov_montant
        })

    # Reprise ancienne provision
    if montant_reprise_prov > 0:
        ecritures.append({
            "Date": date_ecriture.strftime("%d/%m/%Y"),
            "Journal": journal,
            "Compte": compte_prov_debit,
            "Libelle": f"{libelle_base} - Reprise provision",
            "Analytique": "",
            "Débit": 0.0,
            "Crédit": montant_reprise_prov
        })
        ecritures.append({
            "Date": date_ecriture.strftime("%d/%m/%Y"),
            "Journal": journal,
            "Compte": compte_prov_credit,
            "Libelle": f"{libelle_base} - Reprise provision",
            "Analytique": "",
            "Débit": montant_reprise_prov,
            "Crédit": 0.0
        })

    # ================= DataFrame final =================
    df_ecr = pd.DataFrame(ecritures)

    # Vérification équilibre
    total_debit = round(df_ecr["Débit"].sum(), 2)
    total_credit = round(df_ecr["Crédit"].sum(), 2)

    if total_debit != total_credit:
        st.error(f"⚠️ Écriture déséquilibrée : Débit={total_debit}, Crédit={total_credit}")
    else:
        st.success("✅ Écritures équilibrées !")

    # ================= Export =================
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
