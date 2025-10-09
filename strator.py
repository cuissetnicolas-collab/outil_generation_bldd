import pandas as pd
import numpy as np
from io import BytesIO
import streamlit as st

# ========== Interface utilisateur ==========
st.title("📊 Générateur d'écritures analytiques - BLDD")

# Fichier BLDD
fichier_entree = st.file_uploader("📂 Importer le fichier Excel BLDD", type=["xlsx"])
date_ecriture = st.date_input("📅 Date d'écriture")
journal = st.text_input("📒 Journal", value="VT")
libelle_base = st.text_input("📝 Libellé", value="VENTES BLDD")

# Comptes
compte_ca = "701100000"
compte_retour = "709000000"
compte_remise = "709100000"
compte_com_dist = "622800000"
compte_com_diff = "622800010"
compte_tva_collectee = "445710060"
compte_tva_com = "445660000"
compte_provision = "681000000"
compte_reprise_provision = "467100000"
compte_client = "411100011"

# Saisie montants totaux commissions et reprise provision
com_distribution_total = st.number_input("Montant total commissions distribution", value=1000.00, format="%.2f")
com_diffusion_total = st.number_input("Montant total commissions diffusion", value=500.00, format="%.2f")
provision_reprise = st.number_input("Reprise provision 6 mois", value=0.0, format="%.2f")

# Taux commissions
taux_dist = st.number_input("Taux distribution (%)", value=12.5)/100
taux_diff = st.number_input("Taux diffusion (%)", value=9.0)/100

# ========== Traitement ==========
if fichier_entree is not None:
    df = pd.read_excel(fichier_entree, header=9, dtype={"ISBN": str})
    df.columns = df.columns.str.strip()
    df = df.dropna(subset=["ISBN"]).copy()
    
    df["ISBN"] = df["ISBN"].astype(str).str.strip().str.replace(r'\.0$', '', regex=True)
    df["ISBN"] = df["ISBN"].str.replace('-', '', regex=False).str.replace(' ', '', regex=False)
    
    for c in ["Vente", "Retour", "Net", "Facture"]:
        df[c] = pd.to_numeric(df[c], errors="coerce").fillna(0).round(2)
    
    # ========= Calcul commissions =========
    # Distribution
    raw_dist = df["Vente"] * taux_dist
    scaled_dist = raw_dist * (com_distribution_total / raw_dist.sum())
    cents_floor = np.floor(scaled_dist * 100).astype(int)
    remainders = (scaled_dist * 100) - cents_floor
    diff = int(round(com_distribution_total*100)) - cents_floor.sum()
    idx_sorted = np.argsort(-remainders.values)
    adjust = np.zeros(len(df), dtype=int)
    if diff > 0:
        adjust[idx_sorted[:diff]] = 1
    elif diff < 0:
        adjust[idx_sorted[len(df)+diff:]] = -1
    df["Commission_distribution"] = (cents_floor + adjust)/100.0

    # Diffusion
    raw_diff = df["Net"] * taux_diff
    scaled_diff = raw_diff * (com_diffusion_total / raw_diff.sum())
    cents_floor = np.floor(scaled_diff * 100).astype(int)
    remainders = (scaled_diff * 100) - cents_floor
    diff = int(round(com_diffusion_total*100)) - cents_floor.sum()
    idx_sorted = np.argsort(-remainders.values)
    adjust = np.zeros(len(df), dtype=int)
    if diff > 0:
        adjust[idx_sorted[:diff]] = 1
    elif diff < 0:
        adjust[idx_sorted[len(df)+diff:]] = -1
    df["Commission_diffusion"] = (cents_floor + adjust)/100.0
    
    # ========= Construction écritures par ISBN =========
    ecritures = []
    for _, r in df.iterrows():
        # CA brut
        ecritures.append({
            "Date": date_ecriture.strftime("%d/%m/%Y"), "Journal": journal, "Compte": compte_ca,
            "Libelle": f"{libelle_base} - CA brut", "ISBN": r["ISBN"],
            "Débit": 0.0, "Crédit": max(0,r["Vente"])
        })
        # Retours
        ecritures.append({
            "Date": date_ecriture.strftime("%d/%m/%Y"), "Journal": journal, "Compte": compte_retour,
            "Libelle": f"{libelle_base} - Retours", "ISBN": r["ISBN"],
            "Débit": abs(r["Retour"]), "Crédit": 0.0
        })
        # Remises libraires
        remise = r["Net"] - r["Facture"]
        if remise != 0:
            ecritures.append({
                "Date": date_ecriture.strftime("%d/%m/%Y"), "Journal": journal, "Compte": compte_remise,
                "Libelle": f"{libelle_base} - Remises libraires", "ISBN": r["ISBN"],
                "Débit": remise if remise>0 else 0.0,
                "Crédit": abs(remise) if remise<0 else 0.0
            })
        # Commissions distribution
        com_dist = r["Commission_distribution"]
        if com_dist !=0:
            ecritures.append({
                "Date": date_ecriture.strftime("%d/%m/%Y"), "Journal": journal, "Compte": compte_com_dist,
                "Libelle": f"{libelle_base} - Com. distribution", "ISBN": r["ISBN"],
                "Débit": com_dist if com_dist>0 else 0.0,
                "Crédit": abs(com_dist) if com_dist<0 else 0.0
            })
        # Commissions diffusion
        com_diff = r["Commission_diffusion"]
        if com_diff !=0:
            ecritures.append({
                "Date": date_ecriture.strftime("%d/%m/%Y"), "Journal": journal, "Compte": compte_com_diff,
                "Libelle": f"{libelle_base} - Com. diffusion", "ISBN": r["ISBN"],
                "Débit": com_diff if com_diff>0 else 0.0,
                "Crédit": abs(com_diff) if com_diff<0 else 0.0
            })
        # Provision 10% TTC sur CA brut
        provision_ttc = round(r["Vente"]*1.055*0.10,2)  # TTC à 5,5%
        if provision_ttc !=0:
            ecritures.append({
                "Date": date_ecriture.strftime("%d/%m/%Y"), "Journal": journal, "Compte": compte_provision,
                "Libelle": f"{libelle_base} - Provision retours", "ISBN": r["ISBN"],
                "Débit": provision_ttc, "Crédit": 0.0
            })

    df_ecr = pd.DataFrame(ecritures)

    # ========= Lignes globales =========
    ca_net_total = df["Facture"].sum()
    com_total = df["Commission_distribution"].sum() + df["Commission_diffusion"].sum()
    tva_collectee_total = round(ca_net_total*0.055,2)
    tva_com_total = round(com_total*0.055,2)
    provision_total = round((df["Vente"]*1.055*0.10).sum(),2)

    # TVA collectée
    df_ecr = pd.concat([df_ecr, pd.DataFrame([{
        "Date": date_ecriture.strftime("%d/%m/%Y"), "Journal": journal,
        "Compte": compte_tva_collectee, "Libelle": f"{libelle_base} - TVA collectée",
        "ISBN": "", "Débit": 0.0, "Crédit": tva_collectee_total
    }])], ignore_index=True)

    # TVA déductible commissions
    df_ecr = pd.concat([df_ecr, pd.DataFrame([{
        "Date": date_ecriture.strftime("%d/%m/%Y"), "Journal": journal,
        "Compte": compte_tva_com, "Libelle": f"{libelle_base} - TVA déductible commissions",
        "ISBN": "", "Débit": tva_com_total, "Crédit": 0.0
    }])], ignore_index=True)

    # Reprise provision (écriture inverse)
    if provision_reprise !=0:
        df_ecr = pd.concat([df_ecr, pd.DataFrame([{
            "Date": date_ecriture.strftime("%d/%m/%Y"), "Journal": journal,
            "Compte": compte_reprise_provision, "Libelle": f"{libelle_base} - Reprise provision",
            "ISBN": "", "Débit": provision_reprise, "Crédit": 0.0
        }, {
            "Date": date_ecriture.strftime("%d/%m/%Y"), "Journal": journal,
            "Compte": compte_client, "Libelle": f"{libelle_base} - Reprise provision client",
            "ISBN": "", "Débit": 0.0, "Crédit": provision_reprise
        }])], ignore_index=True)

    # Compte client global 411
    solde_client = ca_net_total - tva_collectee_total - com_total - tva_com_total - provision_total + provision_reprise
    df_ecr = pd.concat([df_ecr, pd.DataFrame([{
        "Date": date_ecriture.strftime("%d/%m/%Y"), "Journal": journal,
        "Compte": compte_client, "Libelle": f"{libelle_base} - Contrepartie client",
        "ISBN": "", "Débit": solde_client, "Crédit": 0.0
    }])], ignore_index=True)

    # Vérification équilibre
    total_debit = round(df_ecr["Débit"].sum(),2)
    total_credit = round(df_ecr["Crédit"].sum(),2)
    if total_debit != total_credit:
        st.error(f"⚠️ Écritures déséquilibrées : Débit={total_debit}, Crédit={total_credit}")
    else:
        st.success("✅ Écritures équilibrées !")

    # Export & téléchargement
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
