import pandas as pd
import numpy as np
from io import BytesIO
import streamlit as st

# ============================
# Interface utilisateur
# ============================
st.title("📊 Générateur d'écritures analytiques - BLDD")

# Import du fichier
fichier_entree = st.file_uploader("📂 Importer le fichier Excel BLDD", type=["xlsx"])
date_ecriture = st.date_input("📅 Date d'écriture")
journal = st.text_input("📒 Journal", value="VT")
libelle_base = st.text_input("📝 Libellé", value="VENTES BLDD")

# Comptes utilisés
compte_ca = "701100000"
compte_retour = "709000000"
compte_remise = "709100000"
compte_com_dist = "622800000"
compte_com_diff = "622800010"
compte_tva_collectee = "445710060"
compte_tva_com = "445660000"
compte_provision = "681000000"
compte_reprise = "467100000"
compte_client = "411100011"

# Saisie montants totaux commissions et reprise provision
com_distribution_total = st.number_input("Montant total commissions distribution", value=1000.00, format="%.2f")
com_diffusion_total = st.number_input("Montant total commissions diffusion", value=500.00, format="%.2f")
provision_reprise = st.number_input("Montant de reprise de provision (6 mois)", value=0.0, format="%.2f")

# Taux commissions
taux_dist = st.number_input("Taux distribution (%)", value=12.5) / 100
taux_diff = st.number_input("Taux diffusion (%)", value=9.0) / 100

# ============================
# Traitement
# ============================
if fichier_entree is not None:
    df = pd.read_excel(fichier_entree, header=9, dtype={"ISBN": str})
    df.columns = df.columns.str.strip()
    df = df.dropna(subset=["ISBN"]).copy()

    df["ISBN"] = (
        df["ISBN"].astype(str)
        .str.strip()
        .str.replace(r"\.0$", "", regex=True)
        .str.replace("-", "", regex=False)
        .str.replace(" ", "", regex=False)
    )

    for c in ["Vente", "Retour", "Net", "Facture"]:
        df[c] = pd.to_numeric(df[c], errors="coerce").fillna(0).round(2)

    # ============================
    # Calcul commissions
    # ============================
    def repartir_commissions(montants, total):
        raw = montants.copy()
        scaled = raw * (total / raw.sum())
        cents_floor = np.floor(scaled * 100).astype(int)
        remainders = (scaled * 100) - cents_floor
        diff = int(round(total * 100)) - cents_floor.sum()
        idx_sorted = np.argsort(-remainders.values)
        adjust = np.zeros(len(raw), dtype=int)
        if diff > 0:
            adjust[idx_sorted[:diff]] = 1
        elif diff < 0:
            adjust[idx_sorted[len(raw) + diff :]] = -1
        return (cents_floor + adjust) / 100.0

    df["Commission_distribution"] = repartir_commissions(df["Vente"], com_distribution_total)
    df["Commission_diffusion"] = repartir_commissions(df["Net"], com_diffusion_total)

    # ============================
    # Construction écritures
    # ============================
    ecritures = []

    for _, r in df.iterrows():
        isbn = r["ISBN"]
        # CA brut
        ecritures.append({
            "Date": date_ecriture.strftime("%d/%m/%Y"), "Journal": journal,
            "Compte": compte_ca, "Libelle": f"{libelle_base} - CA brut", "ISBN": isbn,
            "Débit": 0.0, "Crédit": max(0, r["Vente"])
        })
        # Retours
        ecritures.append({
            "Date": date_ecriture.strftime("%d/%m/%Y"), "Journal": journal,
            "Compte": compte_retour, "Libelle": f"{libelle_base} - Retours", "ISBN": isbn,
            "Débit": abs(r["Retour"]), "Crédit": 0.0
        })
        # Remises libraires
        remise = r["Net"] - r["Facture"]
        if remise != 0:
            ecritures.append({
                "Date": date_ecriture.strftime("%d/%m/%Y"), "Journal": journal,
                "Compte": compte_remise, "Libelle": f"{libelle_base} - Remises libraires", "ISBN": isbn,
                "Débit": 0.0 if remise < 0 else remise,
                "Crédit": abs(remise) if remise < 0 else 0.0
            })
        # Commissions distribution
        com_dist = r["Commission_distribution"]
        if com_dist != 0:
            ecritures.append({
                "Date": date_ecriture.strftime("%d/%m/%Y"), "Journal": journal,
                "Compte": compte_com_dist, "Libelle": f"{libelle_base} - Com. distribution", "ISBN": isbn,
                "Débit": com_dist if com_dist > 0 else 0.0,
                "Crédit": abs(com_dist) if com_dist < 0 else 0.0
            })
        # Commissions diffusion
        com_diff = r["Commission_diffusion"]
        if com_diff != 0:
            ecritures.append({
                "Date": date_ecriture.strftime("%d/%m/%Y"), "Journal": journal,
                "Compte": compte_com_diff, "Libelle": f"{libelle_base} - Com. diffusion", "ISBN": isbn,
                "Débit": com_diff if com_diff > 0 else 0.0,
                "Crédit": abs(com_diff) if com_diff < 0 else 0.0
            })

    df_ecr = pd.DataFrame(ecritures)

    # ============================
    # Totaux globaux
    # ============================
    ca_net_total = df["Facture"].sum()
    ca_brut_total = df["Vente"].sum()
    retour_total = df["Retour"].sum()
    remise_total = (df["Net"] - df["Facture"]).sum()
    com_total = df["Commission_distribution"].sum() + df["Commission_diffusion"].sum()
    tva_collectee = round(ca_net_total * 0.055, 2)
    tva_com = round(com_total * 0.055, 2)

    # Provision sur CA brut TTC
    provision = round(ca_brut_total * 1.055 * 0.10, 2)

    # ============================
    # Lignes globales
    # ============================
    lignes_globales = [
        # TVA collectée
        {"Compte": compte_tva_collectee, "Libelle": f"{libelle_base} - TVA collectée", "Débit": 0.0, "Crédit": tva_collectee},
        # TVA déductible sur commissions
        {"Compte": compte_tva_com, "Libelle": f"{libelle_base} - TVA déductible commissions", "Débit": tva_com, "Crédit": 0.0},
        # Provision retours (681)
        {"Compte": compte_provision, "Libelle": f"{libelle_base} - Provision retours", "Débit": provision, "Crédit": 0.0},
        # Reprise de provision (467 au débit / 411 au crédit)
        {"Compte": compte_reprise, "Libelle": f"{libelle_base} - Reprise provision", "Débit": provision_reprise, "Crédit": 0.0},
        {"Compte": compte_client, "Libelle": f"{libelle_base} - Reprise provision (contrepartie)", "Débit": 0.0, "Crédit": provision_reprise},
    ]

    # Calcul du solde client global (équilibrage)
    solde_client = ca_net_total - tva_collectee - com_total - tva_com - provision + provision_reprise
    lignes_globales.append({
        "Compte": compte_client,
        "Libelle": f"{libelle_base} - Contrepartie client",
        "Débit": solde_client, "Crédit": 0.0
    })

    df_glob = pd.DataFrame(lignes_globales)
    df_glob["Date"] = date_ecriture.strftime("%d/%m/%Y")
    df_glob["Journal"] = journal
    df_glob["ISBN"] = ""

    # ============================
    # Fusion et vérification
    # ============================
    df_final = pd.concat([df_ecr, df_glob], ignore_index=True)
    total_debit = round(df_final["Débit"].sum(), 2)
    total_credit = round(df_final["Crédit"].sum(), 2)

    if abs(total_debit - total_credit) > 0.01:
        st.error(f"⚠️ Écritures déséquilibrées : Débit={total_debit}, Crédit={total_credit}")
    else:
        st.success("✅ Écritures équilibrées !")

    # ============================
    # Export
    # ============================
    buffer = BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        df_final.to_excel(writer, index=False, sheet_name="Ecritures")
    buffer.seek(0)

    st.download_button(
        label="📥 Télécharger les écritures (Excel)",
        data=buffer,
        file_name="Ecritures_BLDD.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )

    # Aperçu
    st.subheader("👀 Aperçu des écritures générées")
    st.dataframe(df_final)
