import pandas as pd
from datetime import date

# --- PARAMÈTRES UTILISATEUR ---
date_du_jour = date.today().strftime("%d/%m/%Y")

# Exemple de dataframe d'entrée
# df = pd.read_excel("fichier_bldd.xlsx")

# --- CALCULS DES MONTANTS ---
df["Remise_libraire"] = df["Net"] - df["Facture"]

# Corriger les retours négatifs => positifs
df["Retour"] = df["Retour"].abs()

# --- LISTE DES ÉCRITURES ---
entries = []

# Parcours par ISBN
for isbn, data in df.groupby("ISBN"):
    vente = data["Vente"].sum()
    retour = data["Retour"].sum()
    remise = data["Remise_libraire"].sum()
    net = data["Net"].sum()

    # --- CA brut ---
    entries.append({
        "Date": date_du_jour,
        "Journal": "VE",
        "Compte": "701100000",
        "Libellé": f"CA Brut {isbn}",
        "Débit": 0.0,
        "Crédit": round(vente, 2),
        "Analytique": isbn
    })

    # --- Retours ---
    entries.append({
        "Date": date_du_jour,
        "Journal": "VE",
        "Compte": "709000000",
        "Libellé": f"Retours {isbn}",
        "Débit": round(retour, 2),
        "Crédit": 0.0,
        "Analytique": isbn
    })

    # --- Remises libraires ---
    if remise >= 0:
        entries.append({
            "Date": date_du_jour,
            "Journal": "VE",
            "Compte": "709100000",
            "Libellé": f"Remise libraire {isbn}",
            "Débit": round(remise, 2),
            "Crédit": 0.0,
            "Analytique": isbn
        })
    else:
        entries.append({
            "Date": date_du_jour,
            "Journal": "VE",
            "Compte": "709100000",
            "Libellé": f"Remise libraire {isbn}",
            "Débit": 0.0,
            "Crédit": round(abs(remise), 2),
            "Analytique": isbn
        })

# --- COMMISSIONS DISTRIBUTION / DIFFUSION ---
montant_commission_distribution = float(input("Montant total commission distribution : "))
montant_commission_diffusion = float(input("Montant total commission diffusion : "))

# TVA sur commissions (déductible)
tva_commissions = (montant_commission_distribution + montant_commission_diffusion) * 0.055

entries.append({
    "Date": date_du_jour,
    "Journal": "OD",
    "Compte": "622800000",
    "Libellé": "Commission distribution",
    "Débit": round(montant_commission_distribution, 2),
    "Crédit": 0.0,
    "Analytique": ""
})

entries.append({
    "Date": date_du_jour,
    "Journal": "OD",
    "Compte": "622800010",
    "Libellé": "Commission diffusion",
    "Débit": round(montant_commission_diffusion, 2),
    "Crédit": 0.0,
    "Analytique": ""
})

entries.append({
    "Date": date_du_jour,
    "Journal": "OD",
    "Compte": "445660",
    "Libellé": "TVA déductible sur commissions",
    "Débit": round(tva_commissions, 2),
    "Crédit": 0.0,
    "Analytique": ""
})

# --- TVA COLLECTÉE (CA net après remise et retours) ---
ca_net = (df["Net"] - df["Retour"].fillna(0)).sum()
tva_collectee = ca_net * 0.055

entries.append({
    "Date": date_du_jour,
    "Journal": "VE",
    "Compte": "445710060",
    "Libellé": "TVA collectée sur ventes",
    "Débit": 0.0,
    "Crédit": round(tva_collectee, 2),
    "Analytique": ""
})

# --- PROVISIONS (10 % du CA brut TTC avant retours/remises) ---
provision_entries = []
total_provision = 0

for isbn, data in df.groupby("ISBN"):
    montant_brut_ttc = data["Vente"].sum() * 1.055
    provision = montant_brut_ttc * 0.10
    total_provision += provision

    # Écriture analytique pour la dotation
    provision_entries.append({
        "Date": date_du_jour,
        "Journal": "OD",
        "Compte": "681500",
        "Libellé": f"Dotation provision {isbn}",
        "Débit": round(provision, 2),
        "Crédit": 0.0,
        "Analytique": isbn
    })

# Contrepartie globale - compte 151
provision_entries.append({
    "Date": date_du_jour,
    "Journal": "OD",
    "Compte": "151000",
    "Libellé": "Dotation provisions - global",
    "Débit": 0.0,
    "Crédit": round(total_provision, 2),
    "Analytique": ""
})

# Reprise (écriture inverse)
provision_entries.append({
    "Date": date_du_jour,
    "Journal": "OD",
    "Compte": "151000",
    "Libellé": "Reprise provisions - global",
    "Débit": round(total_provision, 2),
    "Crédit": 0.0,
    "Analytique": ""
})

provision_entries.append({
    "Date": date_du_jour,
    "Journal": "OD",
    "Compte": "781500",
    "Libellé": "Reprise provisions - global",
    "Débit": 0.0,
    "Crédit": round(total_provision, 2),
    "Analytique": ""
})

entries += provision_entries

# --- COMPTE CLIENT GLOBAL ---
total_ventes = df["Vente"].sum()
total_retours = df["Retour"].sum()
total_remises = df["Remise_libraire"].sum()

montant_client = (
    total_ventes
    - total_retours
    - total_remises
    - montant_commission_distribution
    - montant_commission_diffusion
    - tva_commissions
    - total_provision
    + total_provision  # reprise
    - tva_collectee
)

entries.append({
    "Date": date_du_jour,
    "Journal": "VE",
    "Compte": "411100011",
    "Libellé": "Clients ventes nettes",
    "Débit": round(montant_client, 2),
    "Crédit": 0.0,
    "Analytique": ""
})

# --- CRÉATION DU DATAFRAME FINAL ---
df_ecritures = pd.DataFrame(entries)
cols = ["Date", "Journal", "Compte", "Libellé", "Débit", "Crédit", "Analytique"]
df_ecritures = df_ecritures[cols]

# Tri par ISBN (pour regrouper les écritures analytiques ensemble)
df_ecritures.sort_values(by=["Analytique", "Compte"], inplace=True, ignore_index=True)

# Export possible vers Excel
# df_ecritures.to_excel("Ecritures_Comptables.xlsx", index=False)
