import pandas as pd
import numpy as np
import streamlit as st
from io import BytesIO

st.title("📘 Générateur d'écritures comptables - BLDD")

# === Paramètres ===
fichier_entree = st.file_uploader("📂 Importer le fichier Excel BLDD", type=["xlsx"])
date_ecriture = st.date_input("📅 Date d'écriture")
journal = st.text_input("📒 Journal", value="VT")
libelle_base = st.text_input("📝 Libellé", value="Ventes BLDD")

# Comptes comptables
compte_ca = "701100000"
compte_retour = "709000000"
compte_remise = "709100000"
compte_com_dist = "622800000"
compte_com_diff = "622800010"
compte_tva_collectee = "445710060"
compte_tva_deductible = "445660"
compte_prov_charge = "681"
compte_prov_passif = "151"
compte_client = "411100011"

# Taux et montants
taux_tva = 0.055
taux_provision_retour = 0.10

taux_dist = st.number_input("Taux distribution (%)", value=12.5) / 100
taux_diff = st.number_input("Taux diffusion (%)", value=9.0) / 100
com_distribution_total = st.number_input("Montant total commissions distribution", value=1000.00, format="%.2f")
com_diffusion_total = st.number_input("Montant total commissions diffusion", value=500.00, format="%.2f")

montant_reprise_provision = st.number_input("Montant reprise provision précédente TTC", value=0.00, format="%.2f")

if fichier_entree is not None:
    df = pd.read_excel(fichier_entree, skiprows=8)
    df.columns = df.columns.str.strip()

    # Nettoyage et calculs de base
    df = df.dropna(subset=["ISBN"]).copy()
    df["ISBN"] = df["ISBN"].astype(str).str.replace(r'\.0$', '', regex=True)

    # Conversion des montants
    for c in ["Vente", "Retour", "Net", "Facture"]:
        df[c] = pd.to_numeric(df[c], errors="coerce").fillna(0.0)

    # Valeurs absolues pour les retours
    df["Retour"] = df["Retour"].abs()

    # Calcul de la remise libraire
    df["Remise_libraire"] = df["Net"] - df["Facture"]

    # === Calcul des commissions ===
    def calcul_commissions(df, base_col, taux, montant_total):
        raw = df[base_col] * taux
        sum_raw = raw.sum()
        scaled = raw * (montant_total / sum_raw) if sum_raw != 0 else 0
        cents_floor = np.floor(scaled * 100).astype(int)
        remainders = (scaled * 100) - cents_floor
        target_cents = int(round(montant_total * 100))
        diff = target_cents - cents_floor.sum()
        idx_sorted = np.argsort(-remainders.values)
        adjust = np.zeros(len(df), dtype=int)
        if diff > 0:
            adjust[idx_sorted[:diff]] = 1
        elif diff < 0:
            adjust[idx_sorted[len(df) + diff:]] = -1
        return (cents_floor + adjust) / 100.0

    df["Com_distribution"] = calcul_commissions(df, "Vente", taux_dist, com_distribution_total)
    df["Com_diffusion"] = calcul_commissions(df, "Net", taux_diff, com_diffusion_total)

    # === Calculs TVA et provisions ===
    ca_net = df["Facture"].sum()
    tva_collectee = ca_net * taux_tva

    prov_ttc = (df["Vente"].sum() * (1 + taux_tva)) * taux_provision_retour

    # === Construction des écritures ===
    ecritures = []

    for _, r in df.iterrows():
        isbn = r["ISBN"]

        # Ventes brutes
        ecritures.append({
            "Date": date_ecriture, "Journal": journal, "Compte": compte_ca,
            "Libellé": f"{libelle_base} - CA Brut", "ISBN": isbn,
            "Débit": 0.0, "Crédit": r["Vente"]
        })

        # Retours
        ecritures.append({
            "Date": date_ecriture, "Journal": journal, "Compte": compte_retour,
            "Libellé": f"{libelle_base} - Retours", "ISBN": isbn,
            "Débit": r["Retour"], "Crédit": 0.0
        })

        # Remises libraires
        remise = r["Remise_libraire"]
        if remise >= 0:
            ecritures.append({
                "Date": date_ecriture, "Journal": journal, "Compte": compte_remise,
                "Libellé": f"{libelle_base} - Remise libraire", "ISBN": isbn,
                "Débit": remise, "Crédit": 0.0
            })
        else:
            ecritures.append({
                "Date": date_ecriture, "Journal": journal, "Compte": compte_remise,
                "Libellé": f"{libelle_base} - Remise libraire (retour)", "ISBN": isbn,
                "Débit": 0.0, "Crédit": abs(remise)
            })

        # Commissions
        for col, compte in [("Com_distribution", compte_com_dist), ("Com_diffusion", compte_com_diff)]:
            val = r[col]
            if val >= 0:
                ecritures.append({
                    "Date": date_ecriture, "Journal": journal, "Compte": compte,
                    "Libellé": f"{libelle_base} - {col}", "ISBN": isbn,
                    "Débit": val, "Crédit": 0.0
                })
            else:
                ecritures.append({
                    "Date": date_ecriture, "Journal": journal, "Compte": compte,
                    "Libellé": f"{libelle_base} - {col}", "ISBN": isbn,
                    "Débit": 0.0, "Crédit": abs(val)
                })

        # Provision analytique
        ecritures.append({
            "Date": date_ecriture, "Journal": journal, "Compte": compte_prov_charge,
            "Libellé": f"{libelle_base} - Provision retour (10%)", "ISBN": isbn,
            "Débit": (r["Vente"] * (1 + taux_tva)) * taux_provision_retour, "Crédit": 0.0
        })

    # Provision globale passif
    ecritures.append({
        "Date": date_ecriture, "Journal": journal, "Compte": compte_prov_passif,
        "Libellé": f"{libelle_base} - Provision retour globale (10%)",
        "ISBN": "", "Débit": 0.0, "Crédit": prov_ttc
    })

    # Reprise provision précédente
    if montant_reprise_provision > 0:
        ecritures.append({
            "Date": date_ecriture, "Journal": journal, "Compte": compte_prov_passif,
            "Libellé": f"{libelle_base} - Reprise provision précédente", "ISBN": "",
            "Débit": montant_reprise_provision, "Crédit": 0.0
        })
        ecritures.append({
            "Date": date_ecriture, "Journal": journal, "Compte": compte_prov_charge,
            "Libellé": f"{libelle_base} - Reprise provision précédente", "ISBN": "",
            "Débit": 0.0, "Crédit": montant_reprise_provision
        })

    # TVA collectée
    ecritures.append({
        "Date": date_ecriture, "Journal": journal, "Compte": compte_tva_collectee,
        "Libellé": f"{libelle_base} - TVA collectée", "ISBN": "",
        "Débit": 0.0, "Crédit": tva_collectee
    })

    # TVA déductible (une seule ligne)
    tva_deductible = (com_distribution_total + com_diffusion_total) * taux_tva
    ecritures.append({
        "Date": date_ecriture, "Journal": journal, "Compte": compte_tva_deductible,
        "Libellé": f"{libelle_base} - TVA déductible commissions", "ISBN": "",
        "Débit": tva_deductible, "Crédit": 0.0
    })

    # Compte client global
    total_credit = sum(e["Crédit"] for e in ecritures)
    total_debit = sum(e["Débit"] for e in ecritures)
    solde_client = round(total_credit - total_debit, 2)

    ecritures.append({
        "Date": date_ecriture, "Journal": journal, "Compte": compte_client,
        "Libellé": f"{libelle_base} - Client BLDD", "ISBN": "",
        "Débit": solde_client if solde_client > 0 else 0.0,
        "Crédit": abs(solde_client) if solde_client < 0 else 0.0
    })

    # === Finalisation ===
    df_ecr = pd.DataFrame(ecritures)

    total_debit = df_ecr["Débit"].sum().round(2)
    total_credit = df_ecr["Crédit"].sum().round(2)

    if total_debit != total_credit:
        st.error(f"⚠️ Écriture déséquilibrée : Débit={total_debit} / Crédit={total_credit}")
    else:
        st.success("✅ Écritures équilibrées !")

    # Export Excel
    buffer = BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        df_ecr.to_excel(writer, index=False, sheet_name="Ecritures")
    buffer.seek(0)

    st.download_button(
        label="📥 Télécharger les écritures comptables",
        data=buffer,
        file_name="Ecritures_BLDD.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )

    st.subheader("📘 Aperçu des écritures")
    st.dataframe(df_ecr)
