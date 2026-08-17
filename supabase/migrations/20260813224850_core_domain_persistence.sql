-- Core domain persistence: competitions, teams, seasons, provider identity
-- mappings (ADR-013, ADR-014, ADR-015). Static schema only -- no seed data,
-- no RLS/privilege changes, no polymorphic mapping-target enforcement
-- (ADR-015 decision 8: that boundary is enforced by the application/storage
-- write layer, not by this schema).

CREATE TABLE public.competitions (
    competition_id TEXT NOT NULL,
    name TEXT NOT NULL,
    country TEXT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT competitions_pkey PRIMARY KEY (competition_id),
    CONSTRAINT competitions_competition_id_nonblank CHECK (btrim(competition_id) <> ''),
    CONSTRAINT competitions_name_nonblank CHECK (btrim(name) <> ''),
    CONSTRAINT competitions_country_nonblank CHECK (country IS NULL OR btrim(country) <> '')
);

CREATE TABLE public.teams (
    team_id TEXT NOT NULL,
    name TEXT NOT NULL,
    country TEXT NULL,
    national BOOLEAN NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT teams_pkey PRIMARY KEY (team_id),
    CONSTRAINT teams_team_id_nonblank CHECK (btrim(team_id) <> ''),
    CONSTRAINT teams_name_nonblank CHECK (btrim(name) <> ''),
    CONSTRAINT teams_country_nonblank CHECK (country IS NULL OR btrim(country) <> '')
);

CREATE TABLE public.seasons (
    competition_id TEXT NOT NULL,
    start_year INTEGER NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT seasons_pkey PRIMARY KEY (competition_id, start_year),
    CONSTRAINT seasons_competition_id_fkey FOREIGN KEY (competition_id)
        REFERENCES public.competitions (competition_id)
        ON DELETE RESTRICT
        ON UPDATE NO ACTION,
    CONSTRAINT seasons_start_year_range CHECK (start_year BETWEEN 1000 AND 9999)
);

CREATE TABLE public.provider_identity_mappings (
    provider TEXT NOT NULL,
    entity_type TEXT NOT NULL,
    provider_entity_id TEXT NOT NULL,
    footcap_entity_id TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT provider_identity_mappings_pkey PRIMARY KEY (provider, entity_type, provider_entity_id),
    CONSTRAINT provider_identity_mappings_provider_nonblank CHECK (btrim(provider) <> ''),
    CONSTRAINT provider_identity_mappings_entity_type_nonblank CHECK (btrim(entity_type) <> ''),
    CONSTRAINT provider_identity_mappings_provider_entity_id_nonblank CHECK (btrim(provider_entity_id) <> ''),
    CONSTRAINT provider_identity_mappings_footcap_entity_id_nonblank CHECK (btrim(footcap_entity_id) <> '')
);
