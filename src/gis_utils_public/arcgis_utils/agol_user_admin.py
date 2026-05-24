"""AGOL group administration helpers."""

import re
import sys

from arcgis.gis import GIS  # type: ignore[import-untyped]


def agol_add_users_to_group(
    gis: GIS,
    oidc_brukere: list[str],
    arcgis_brukere: list[str],
    gruppe_navn: str,
    dry_run: bool = True,
    batch_size: int = 10,
) -> None:
    """
    Søk etter brukere i to lister og legg dem til en eksisterende gruppe.
    :param gis:                       Authenticated GIS object (I praksis GIS("home"))
    :param oidc_brukere:              Liste med e-post adresser som skal legges til
    :param arcgis_brukere:            Liste med brukernavn som skal legges til
    :param gruppe_navn:               Navn på AGOL gruppe
    :param dry_run:                   Må settes til False for å gjøre endringer.
    :param batch_size:                Antall brukere per remove_users/add_users-kall
    :return: None.
    """

    print(
        f">>> AGOL organisasjon:            {gis.properties.urlKey}\n"
        f">>> OIDC-brukere input:           {oidc_brukere}\n"
        f">>> ArcGIS-brukere input:         {arcgis_brukere}\n"
        f">>> Gruppe:                       {gruppe_navn}\n"
        f">>> Dry-Run:                      {dry_run}"
    )

    if batch_size < 1:
        sys.exit("batch_size må være >= 1")

    # Avbryt om det finnes duplikater i input-listene
    oidc_brukere = [x.lower() for x in oidc_brukere]
    duplikat_oidc = set(x for x in oidc_brukere if oidc_brukere.count(x) > 1)
    if duplikat_oidc:
        sys.exit(f"duplikat i oidc_brukere {duplikat_oidc}")

    arcgis_brukere = [x.lower() for x in arcgis_brukere]
    duplikat_arcgis = set(x for x in arcgis_brukere if arcgis_brukere.count(x) > 1)
    duplikat_arcgis = {x.lower() for x in arcgis_brukere if arcgis_brukere.count(x) > 1}

    if duplikat_arcgis:
        sys.exit(f"duplikat i arcgis_brukere {duplikat_arcgis}")

    # Finn gruppe
    try:
        grupper_resultat = gis.groups.search(gruppe_navn, max_groups=1)
    except Exception as e:
        sys.exit(f"Feil ved søk etter gruppe '{gruppe_navn}': {e}")

    if not grupper_resultat:
        sys.exit(f"Finner ikke gruppe med navn: {gruppe_navn}")

    # Hent eksisterende medlemmer i gruppen
    gruppe = grupper_resultat[0]
    gruppe_medlemmer = gruppe.get_members()
    # Fjerner ikke owner eller admins
    print(f">>> Gruppe eier:                  {gruppe_medlemmer['owner']}")
    print(f">>> Gruppe admins:                {gruppe_medlemmer['admins']}")

    gruppe_medlemmer_users_oidc = []
    gruppe_medlemmer_users_arcgis = []
    email_regex = re.compile(r"^.*@.*\..*$")

    for u in gruppe_medlemmer["users"]:
        if email_regex.match(u):
            gruppe_medlemmer_users_oidc.append(u)
        else:
            gruppe_medlemmer_users_arcgis.append(u)

    # Fjern OIDC-brukere
    print(f">>> Eksisterende OIDC-brukerne:   {gruppe_medlemmer_users_oidc}")
    if gruppe_medlemmer_users_oidc:
        print(
            f"Fjerner {len(gruppe_medlemmer_users_oidc)} eksisterende OIDC brukere fra gruppen (har epost-adresse som brukernavn)"
        )
        total_batches = (
            len(gruppe_medlemmer_users_oidc) + batch_size - 1
        ) // batch_size
        for start_index in range(0, len(gruppe_medlemmer_users_oidc), batch_size):
            users_batch = gruppe_medlemmer_users_oidc[
                start_index : start_index + batch_size
            ]
            batch_no = start_index // batch_size + 1
            print(
                f"Fjerner OIDC batch {batch_no}/{total_batches} ({len(users_batch)} brukere)"
            )
            if not dry_run:
                try:
                    gruppe.remove_users(users_batch)
                except Exception as e:
                    sys.exit(
                        f"Feil ved fjerning av OIDC batch {batch_no}/{total_batches}: {e}"
                    )
    else:
        print("Ingen eksisterende brukere å fjerne.")

    # Fjern ArcGIS-brukere - Denne er kommentert ut - normalt er ikke dette nødvendig
    # print(f">>> Eksisterende ArcGIS-brukerne: {gruppe_medlemmer_users_arcgis}")
    # if gruppe_medlemmer_users_arcgis:
    #     print(f"Fjerner {len(gruppe_medlemmer_users_arcgis)} eksisterende ArcGIS brukere fra gruppen (har ikke epost-adresse som brukernavn)")
    #     total_batches = (len(gruppe_medlemmer_users_arcgis) + batch_size - 1) // batch_size
    #     for start_index in range(0, len(gruppe_medlemmer_users_arcgis), batch_size):
    #         users_batch = gruppe_medlemmer_users_arcgis[start_index:start_index + batch_size]
    #         batch_no = start_index // batch_size + 1
    #         print(f"Fjerner ArcGIS batch {batch_no}/{total_batches} ({len(users_batch)} brukere)")
    #         if not dry_run:
    #             try:
    #                 gruppe.remove_users(users_batch)
    #             except Exception as e:
    #                 sys.exit(f"Feil ved fjerning av ArcGIS batch {batch_no}/{total_batches}: {e}")
    # else:
    #     print("Ingen eksisterende ArcGIS brukere å fjerne.")

    # Legg OIDC-brukere til gruppe
    oidc_brukere_lagt_til = []
    for email in oidc_brukere:
        if email_regex.match(email):
            query = f"email:{email} AND orgid:{gis.properties.id}"
            try:
                search = gis.users.advanced_search(query=query, max_users=1)
            except Exception as e:
                print(f"Exception: Finner ikke OIDC-bruker med email {email}: {e}")
                continue
            brukere_resultat = list(search["results"])
            if brukere_resultat:
                oidc_brukere_lagt_til.append(brukere_resultat[0].username)
            else:
                print(f"Finner ikke OIDC-bruker med email {email}")
        else:
            sys.exit(f"{email} ser ikke ut som en epost-adresse")
    if oidc_brukere_lagt_til:
        print(
            f"Legger til {len(oidc_brukere_lagt_til)} OIDC-brukere i gruppen '{gruppe.title}': {oidc_brukere_lagt_til}"
        )
        total_batches = (len(oidc_brukere_lagt_til) + batch_size - 1) // batch_size
        for start_index in range(0, len(oidc_brukere_lagt_til), batch_size):
            users_batch = oidc_brukere_lagt_til[start_index : start_index + batch_size]
            batch_no = start_index // batch_size + 1
            print(
                f"Legger til OIDC batch {batch_no}/{total_batches} ({len(users_batch)} brukere)"
            )
            if not dry_run:
                try:
                    gruppe.add_users(users_batch)
                except Exception as e:
                    sys.exit(
                        f"Feil ved adding av OIDC batch {batch_no}/{total_batches}: {e}"
                    )
    else:
        print("Ingen brukere i OIDCC-brukere input funnet – ingen ble lagt til.")

    # Legg ArcGIS-brukere til gruppe, NB! her er ikke brukere slettet siden miljodirektoratet-kontoer må godkjenne at de legges til ei gruppe
    arcgis_brukere_lagt_til = []
    for arcgis_username in arcgis_brukere:
        if not email_regex.match(arcgis_username):
            try:
                bruker = gis.users.get(arcgis_username)
            except Exception as e:
                print(
                    f"Exception: Finner ikke ArcGIS-bruker med brukernavn {arcgis_username}: {e}"
                )
                continue
            if bruker:
                arcgis_brukere_lagt_til.append(bruker)
            else:
                print(f"Finner ikke ArcGIS-bruker med brukernavn  {arcgis_username}")
        else:
            sys.exit(f"{arcgis_username} ser ut til å være en epost-adresse")
    if arcgis_brukere_lagt_til:
        print(
            f"Legger til {len(arcgis_brukere_lagt_til)} ArcGIS-brukere i gruppen '{gruppe.title}': {arcgis_brukere_lagt_til}"
        )
        total_batches = (len(arcgis_brukere_lagt_til) + batch_size - 1) // batch_size
        for start_index in range(0, len(arcgis_brukere_lagt_til), batch_size):
            users_batch = arcgis_brukere_lagt_til[
                start_index : start_index + batch_size
            ]
            batch_no = start_index // batch_size + 1
            print(
                f"Legger til ArcGIS batch {batch_no}/{total_batches} ({len(users_batch)} brukere)"
            )
            if not dry_run:
                try:
                    gruppe.add_users(users_batch)
                except Exception as e:
                    sys.exit(
                        f"Feil ved adding av ArcGIS batch {batch_no}/{total_batches}: {e}"
                    )
    else:
        print("Ingen brukere i ArcGIS-brukere input funnet - ingen ble lagt til.")
