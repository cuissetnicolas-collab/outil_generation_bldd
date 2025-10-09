import streamlit as st
import pandas as pd
import numpy as np
from io import BytesIO

st.title("📊 Générateur d'écritures analytiques BLDD - par ISBN")

# ====== Import fichier ======
fichier_entree = st.file_uploader("📂 Importer le fichier Excel BLDD", type=["xlsx"])
date_ecriture = st.date_input("📅 Date d'écriture")
journal = st.text_input("📒 Journal", value="VT")
libelle_base = st.text_input("📝 Libellé", value="VENTES BLDD")

# Comptes
compte_ca_brut = st.text_input("💰 Compte CA brut (Vente)", value="70100000")
compte_retour = st.text_input("💰 Compte Retours (Retour)", value="70900000")
compte_net = st.text_input("💰 Compte CA net avant remise", value="70600000")
compte_facture = st.text_input("💰 Compte CA après remise (Facture)", value="70700000")
compte_provision_retour = st.text_input("💰 Provision retours 10% TTC", value="48850000")
compte_com_dist = st.text_input("💰 Compte commissions distribution", value="62280000")
compte_com_diff = st.text_input("💰 Compte commissions diffusion", value="62280001")
compte_tva = st.text_input("💰 Compte TVA collectée", value="44570000")

# Taux et montants
taux_dist = st.number_input("Taux distribution (%)", value=12.5)/100
taux_diff = st.number_input("Taux diffusion (%)", value=9.0)/100
montant_com_dist = st.number_input("Montant total commissions distribution", value=1000.00, format="%.2f")
montant_com_diff = st.number_input("Montant total commissions diffusion", value=500.00, format="%.2f")
tva_taux = st.number_input("Taux TVA (%)", value=5.5)/100  # ou autre taux

# ====== Traitement ======
if fichier_entree is not None:
    df = pd.read_excel(fichier_entree, header=9, dtype={"ISBN": str})
    df.columns = df.columns.str.strip()
    df = df.dropna(subset=["ISBN"]).copy()

    df["ISBN"] = df["ISBN"].astype(str).str.strip().str.replace(r'\.0$', '', regex=True)
    df["ISBN"] = df["ISBN"].str.replace('-', '', regex=False).str.replace(' ', '', regex=False)

    # Colonnes numériques
    for col in ["Vente", "Retour", "Net", "Facture"]:
        df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0).round(2)

    # ========== Commissions ==========
    # Distribution
    raw_dist = df["Net"] * taux_dist
    sum_raw_dist = raw_dist.sum()
    scaled_dist = raw_dist * (montant_com_dist / sum_raw_dist)
    cents_floor = np.floor(scaled_dist*100).astype(int)
    remainders = (scaled_dist*100) - cents_floor
    diff = int(round(montant_com_dist*100)) - cents_floor.sum()
    idx_sorted = np.argsort(-remainders.values)
    adjust = np.zeros(len(df), dtype=int)
    if diff > 0: adjust[idx_sorted[:diff]] = 1
    elif diff < 0: adjust[idx_sorted[len(df)+diff:]] = -1
    df["Commission_distribution"] = (cents_floor + adjust)/100.0

    # Diffusion
    raw_diff = df["Net"] * taux_diff
    sum_raw_diff = raw_diff.sum()
    scaled_diff = raw_diff * (montant_com_diff / sum_raw_diff)
    cents_floor = np.floor(scaled_diff*100).astype(int)
    remainders = (scaled_diff*100) - cents_floor
    diff = int(round(montant_com_diff*100)) - cents_floor.sum()
    idx_sorted = np.argsort(-remainders.values)
    adjust = np.zeros(len(df), dtype=int)
    if diff > 0: adjust[idx_sorted[:diff]] = 1
    elif diff < 0: adjust[idx_sorted[len(df)+diff:]] = -1
    df["Commission_diffusion"] = (cents_floor + adjust)/100.0

    # ========== Construction écritures ==========
    ecritures = []

    # Par ISBN : CA brut, Retour, Net, Facture
    for _, r in df.iterrows():
        # CA brut
        ecritures.append({
            "Date": date_ecriture.strftime("%d/%m/%Y"),
            "Journal": journal,
            "Compte": compte_ca_brut,
            "Libelle": f"{libelle_base} - CA brut",
            "Analytique": r["ISBN"],
            "Débit": 0.0,
            "Crédit": r["Vente"]
        })
        # Retours
        ecritures.append({
            "Date": date_ecriture.strftime("%d/%m/%Y"),
            "Journal": journal,
            "Compte": compte_retour,
            "Libelle": f"{libelle_base} - Retours",
            "Analytique": r["ISBN"],
            "Débit": r["Retour"],
            "Crédit": 0.0
        })
        # Net avant remise
        ecritures.append({
            "Date": date_ecriture.strftime("%d/%m/%Y"),
            "Journal": journal,
            "Compte": compte_net,
            "Libelle": f"{libelle_base} - CA net avant remise",
            "Analytique": r["ISBN"],
            "Débit": 0.0,
            "Crédit": r["Net"]
        })
        # Facture après remise
        ecritures.append({
            "Date": date_ecriture.strftime("%d/%m/%Y"),
            "Journal": journal,
            "Compte": compte_facture,
            "Libelle": f"{libelle_base} - Facture HT après remise",
            "Analytique": r["ISBN"],
            "Débit": 0.0,
            "Crédit": r["Facture"]
        })
        # Commissions distribution
        ecritures.append({
            "Date": date_ecriture.strftime("%d/%m/%Y"),
            "Journal": journal,
            "Compte": compte_com_dist,
            "Libelle": f"{libelle_base} - Com dist",
            "Analytique": r["ISBN"],
            "Débit": r["Commission_distribution"],
            "Crédit": 0.0
        })
        # Commissions diffusion
        ecritures.append({
            "Date": date_ecriture.strftime("%d/%m/%Y"),
            "Journal": journal,
            "Compte": compte_com_diff,
            "Libelle": f"{libelle_base} - Com diff",
            "Analytique": r["ISBN"],
            "Débit": r["Commission_diffusion"],
            "Crédit": 0.0
        })

    # Provisions retours 10% TTC (ligne globale)
    provision_retour = (df["Vente"] - df["Retour"]).sum() * 0.10
    ecritures.append({
        "Date": date_ecriture.strftime("%d/%m/%Y"),
        "Journal": journal,
        "Compte": compte_provision_retour,
        "Libelle": "Provision retours 10% TTC",
        "Analytique": "",
        "Débit": provision_retour,
        "Crédit": 0.0
    })

    # TVA sur Facture (ligne globale)
    tva_total = df["Facture"].sum() * tva_taux
    ecritures.append({
        "Date": date_ecriture.strftime("%d/%m/%Y"),
        "Journal": journal,
        "Compte": compte_tva,
        "Libelle": "TVA collectée",
        "Analytique": "",
        "Débit": 0.0,
        "Crédit": tva_total
    })

    df_ecr = pd.DataFrame(ecritures)

    # Vérification équilibre
    total_debit = round(df_ecr["Débit"].sum(),2)
    total_credit = round(df_ecr["Crédit"].sum(),2)
    if total_debit != total_credit:
        st.error(f"⚠️ Écriture déséquilibrée : Débit={total_debit}, Crédit={total_credit}")
    else:
        st.success("✅ Écritures équilibrées et prêtes à l’import !")

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
    st.subheader("👀 Aperçu des écritures par ISBN")
    st.dataframe(df_ecr)
