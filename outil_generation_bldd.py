import pandas as pd
import numpy as np
from io import BytesIO
import streamlit as st
from pandas.tseries.offsets import MonthEnd

# ============================
# 🔐 AUTHENTIFICATION
# ============================
if "login" not in st.session_state:
    st.session_state["login"] = False
if "username" not in st.session_state:
    st.session_state["username"] = ""
if "name" not in st.session_state:
    st.session_state["name"] = ""

def login(username, password):
    users = {
        "aurore": {"password": "12345", "name": "Aurore Demoulin"},
        "laure.froidefond": {"password": "Laure Froidefond"},
        "Bruno": {"password": "Toto1963$", "name": "Toto El Gringo"},
        "Manana": {"password": "193827", "name": "Manana"},
        "Nicolas": {"password": "29071989", "name": "Nicolas"},
    }
    if username in users and password == users[username]["password"]:
        st.session_state["login"] = True
        st.session_state["username"] = username
        st.session_state["name"] = users[username]["name"]
        st.success(f"Bienvenue {st.session_state['name']} 👋")
    else:
        st.error("❌ Identifiants incorrects")

if not st.session_state["login"]:
    st.title("🔑 Connexion espace expert-comptable")
    username_input = st.text_input("Identifiant")
    password_input = st.text_input("Mot de passe", type="password")
    if st.button("Connexion"):
        login(username_input, password_input)
    st.stop()

if st.sidebar.button("Déconnexion"):
    st.session_state["login"] = False
    st.session_state["username"] = ""
    st.session_state["name"] = ""
    st.success("Vous êtes déconnecté(e).")
    st.stop()

# ============================
# Interface utilisateur
# ============================
st.title("📊 Générateur d'écritures analytiques - BLDD")

fichier_entree = st.file_uploader("📂 Importer le fichier Excel BLDD", type=["xlsx"])
date_ecriture = st.date_input("📅 Date d'écriture")
journal = st.text_input("📒 Journal", value="VT")
libelle_base = st.text_input("📝 Libellé", value="VENTES BLDD")
famille_analytique = st.text_input("🏷️ Famille analytique", value="EDITION")

# Comptes
compte_ca = "701100000"
compte_retour = "709000000"
compte_remise = "709100000"
compte_com_dist = "622800000"
compte_com_diff = "622800010"
compte_tva_collectee = "445710060"
compte_tva_com = "445660000"
compte_provision = "681000000"
compte_reprise = "781000000"
compte_client = "411100011"

com_distribution_total = st.number_input("Montant total commissions distribution", 1000.00, format="%.2f")
com_diffusion_total = st.number_input("Montant total commissions diffusion", 500.00, format="%.2f")

# ============================
# Fonctions utilitaires
# ============================
def repartir_commissions(montants, total):
    montants = montants.clip(lower=0)
    if montants.sum() == 0:
        return np.zeros(len(montants))
    scaled = montants * (total / montants.sum())
    cents = np.floor(scaled * 100).astype(int)
    diff = int(round(total * 100)) - cents.sum()
    if diff != 0:
        idx = (scaled * 100 - cents).sort_values(ascending=False).index[:abs(diff)]
        cents.loc[idx] += np.sign(diff)
    return cents / 100

def add_ligne_signe(ecritures, date, compte, libelle, montant, isbn):
    ecritures.append({
        "Date": date.strftime("%d/%m/%Y"),
        "Journal": journal,
        "Compte": compte,
        "Libelle": libelle,
        "Famille analytique": famille_analytique,
        "ISBN": isbn,
        "Débit": abs(montant) if montant < 0 else 0.0,
        "Crédit": montant if montant > 0 else 0.0
    })

# ============================
# Traitement
# ============================
if fichier_entree:

    df = pd.read_excel(fichier_entree, header=9, dtype={"ISBN": str})
    df.columns = df.columns.str.strip()
    df = df.dropna(subset=["ISBN"]).copy()

    for c in ["Vente", "Retour", "Net", "Facture"]:
        df[c] = pd.to_numeric(df[c], errors="coerce").fillna(0).round(2)

    df["Commission_distribution"] = repartir_commissions(df["Vente"], com_distribution_total)
    df["Commission_diffusion"] = repartir_commissions(df["Net"], com_diffusion_total)

    ecritures = []

    for _, r in df.iterrows():
        isbn = r["ISBN"]

        # CA brut (sens automatique)
        add_ligne_signe(ecritures, date_ecriture, compte_ca,
                        f"{libelle_base} - CA brut", r["Vente"], isbn)

        # Retours
        if r["Retour"] != 0:
            add_ligne_signe(ecritures, date_ecriture, compte_retour,
                            f"{libelle_base} - Retours", -abs(r["Retour"]), isbn)

        # Remises
        remise = r["Net"] - r["Facture"]
        if remise != 0:
            add_ligne_signe(ecritures, date_ecriture, compte_remise,
                            f"{libelle_base} - Remises libraires", -remise, isbn)

        # Commissions
        if r["Commission_distribution"] != 0:
            add_ligne_signe(ecritures, date_ecriture, compte_com_dist,
                            f"{libelle_base} - Com. distribution", -r["Commission_distribution"], isbn)

        if r["Commission_diffusion"] != 0:
            add_ligne_signe(ecritures, date_ecriture, compte_com_diff,
                            f"{libelle_base} - Com. diffusion", -r["Commission_diffusion"], isbn)

        # Provision retours
        provision = round(abs(r["Vente"]) * 1.055 * 0.10, 2)
        if provision > 0:
            sens = 1 if r["Vente"] > 0 else -1
            add_ligne_signe(ecritures, date_ecriture, compte_provision,
                            f"{libelle_base} - Provision retours", provision * sens, isbn)

            reprise_date = pd.to_datetime(date_ecriture) + MonthEnd(6)
            add_ligne_signe(ecritures, reprise_date, compte_reprise,
                            f"{libelle_base} - Reprise provision", -provision * sens, isbn)

    df_ecr = pd.DataFrame(ecritures)

    # TVA
    tva_collectee = round(df["Facture"].sum() * 0.055, 2)
    tva_com = round((df["Commission_distribution"].sum() + df["Commission_diffusion"].sum()) * 0.055, 2)

    df_ecr = pd.concat([df_ecr, pd.DataFrame([
        {"Date": date_ecriture.strftime("%d/%m/%Y"), "Journal": journal, "Compte": compte_tva_collectee,
         "Libelle": f"{libelle_base} - TVA collectée", "Famille analytique": famille_analytique,
         "ISBN": "", "Débit": 0.0, "Crédit": tva_collectee},
        {"Date": date_ecriture.strftime("%d/%m/%Y"), "Journal": journal, "Compte": compte_tva_com,
         "Libelle": f"{libelle_base} - TVA déductible commissions", "Famille analytique": famille_analytique,
         "ISBN": "", "Débit": tva_com, "Crédit": 0.0}
    ])], ignore_index=True)

    # Contrepartie client
    diff = round(df_ecr["Débit"].sum() - df_ecr["Crédit"].sum(), 2)
    df_ecr = pd.concat([df_ecr, pd.DataFrame([{
        "Date": date_ecriture.strftime("%d/%m/%Y"),
        "Journal": journal,
        "Compte": compte_client,
        "Libelle": f"{libelle_base} - Contrepartie client",
        "Famille analytique": famille_analytique,
        "ISBN": "",
        "Débit": abs(diff) if diff < 0 else 0.0,
        "Crédit": diff if diff > 0 else 0.0
    }])], ignore_index=True)

    # Vérification
    ecart = round(df_ecr["Débit"].sum() - df_ecr["Crédit"].sum(), 2)
    st.success("✅ Écritures équilibrées") if ecart == 0 else st.error(f"⚠️ Écart : {ecart}")

    buffer = BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        df_ecr.to_excel(writer, index=False, sheet_name="Ecritures")
    buffer.seek(0)

    st.download_button("📥 Télécharger les écritures", buffer, "Ecritures_BLDD.xlsx")
    st.dataframe(df_ecr)
