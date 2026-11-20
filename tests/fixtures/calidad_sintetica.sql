-- Fixture sintética de `scripts/medicion/censo_calidad.py` (solo para la BD de
-- pruebas, cuyo nombre debe llevar «test»). Un caso por comprobación, con
-- identificadores fijos para que las pruebas puedan afirmar el caso concreto.
--
-- No se ejecuta contra producción. La carga el test `test_censo_calidad_pg`.
-- Las rutas son ficticias; los títulos son inventados o genéricos.

BEGIN;
TRUNCATE publishers, imprints, series, issues, files, wishlist, reading_progress,
         collections, collection_series, story_arcs, story_arc_issues, upgrade_proposals,
         import_runs, library_roots, entity_source_records, field_provenance,
         local_aliases, alias_importado, correspondencias_contexto, declaraciones_carpeta,
         asignacion_operaciones, paquete_operaciones, apartado_operaciones,
         creators, characters
  RESTART IDENTITY CASCADE;

INSERT INTO publishers (id, name, country) VALUES
 ('a0000000-0000-4000-8000-000000000001','DC Comics',NULL),
 ('a0000000-0000-4000-8000-000000000002','DC Cómics',NULL),
 ('a0000000-0000-4000-8000-000000000003','Planeta','España'),
 ('a0000000-0000-4000-8000-000000000004','Marvel',NULL),
 ('a0000000-0000-4000-8000-000000000005','Otra',NULL);

INSERT INTO imprints (id, publisher_id, name) VALUES
 ('a0000000-0000-4000-8000-000000000006','a0000000-0000-4000-8000-000000000001','Vertigo'),
 ('a0000000-0000-4000-8000-000000000007','a0000000-0000-4000-8000-000000000001','VÉRTIGO');

INSERT INTO library_roots (id, name, path, enabled, is_default)
VALUES ('a0000000-0000-4000-8000-000000000000','Biblioteca','/biblioteca',true,true);
CREATE TEMP TABLE _root AS SELECT id, path FROM library_roots ORDER BY created_at LIMIT 1;
INSERT INTO library_roots (id, name, path, enabled, is_default) VALUES
 ('a0000000-0000-4000-8000-000000000008','Subraíz',(SELECT path FROM _root) || '/sub',true,false),
 ('a0000000-0000-4000-8000-000000000009','Apagada','/fuera',false,false);

INSERT INTO series (id, title, kind, tradition, publisher_id, start_year, end_year, total_issues,
                    status, comic_vine_id, anilist_id, tebeosfera_slug, gcd_id, metron_id,
                    open_library_id, fandom_dc_slug, fandom_marvel_slug, cover_url,
                    metadata, metadata_source, enrichment_attempted_at, locked_fields,
                    wishlist_policy, parent_series_id)
VALUES
 ('b0000000-0000-4000-8000-000000000001','Batman','regular','american',
  'a0000000-0000-4000-8000-000000000001',NULL,NULL,50,'ongoing',111,NULL,NULL,NULL,NULL,NULL,NULL,NULL,
  'https://example.invalid/cover.jpg','{"descripcion":"sin procedencia"}'::jsonb,'comic_vine',now(),'{}','faltantes',NULL),
 ('b0000000-0000-4000-8000-000000000002','Superman','regular','american',
  'a0000000-0000-4000-8000-000000000001',1938,NULL,NULL,'ongoing',222,777,NULL,NULL,NULL,NULL,NULL,NULL,NULL,
  '{}'::jsonb,'comic_vine',now(),'{}','ninguno',NULL),
 ('b0000000-0000-4000-8000-000000000003','Batman','regular','american',
  'a0000000-0000-4000-8000-000000000001',2011,NULL,NULL,'ongoing',NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL,
  '{}'::jsonb,NULL,NULL,'{}','ninguno',NULL),
 ('b0000000-0000-4000-8000-000000000004','Batman','regular','american',
  'a0000000-0000-4000-8000-000000000001',2012,NULL,NULL,'ongoing',NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL,
  '{}'::jsonb,NULL,NULL,'{}','ninguno',NULL),
 ('b0000000-0000-4000-8000-000000000005','Mortadelo','regular','tebeo',
  'a0000000-0000-4000-8000-000000000003',1958,NULL,20,'ongoing',333,NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL,
  '{}'::jsonb,'comic_vine',now(),'{}','faltantes',NULL),
 ('b0000000-0000-4000-8000-000000000006','Obra única','one_shot','other',
  'a0000000-0000-4000-8000-000000000005',2020,NULL,NULL,'ongoing',NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL,
  '{}'::jsonb,NULL,NULL,'{}','ninguno',NULL),
 ('b0000000-0000-4000-8000-000000000007','Anual Suelto','annual','american',
  'a0000000-0000-4000-8000-000000000001',2000,1999,NULL,'ongoing',NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL,
  '{}'::jsonb,NULL,NULL,'{}','ninguno',NULL),
 ('b0000000-0000-4000-8000-000000000008','Anual Hijo','annual','american',
  'a0000000-0000-4000-8000-000000000003',2001,NULL,NULL,'ongoing',NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL,
  '{}'::jsonb,NULL,NULL,'{}','ninguno','b0000000-0000-4000-8000-000000000001'),
 ('b0000000-0000-4000-8000-000000000009','Serie Corta','regular','american',
  'a0000000-0000-4000-8000-000000000001',2020,NULL,1,'ongoing',NULL,444,NULL,NULL,NULL,NULL,NULL,NULL,NULL,
  '{}'::jsonb,NULL,NULL,'{}','ninguno',NULL),
 ('b0000000-0000-4000-8000-000000000010','Fandom Mal','regular','american',
  'a0000000-0000-4000-8000-000000000004',2020,NULL,NULL,'ongoing',NULL,NULL,NULL,NULL,NULL,NULL,'batman_vol_1',NULL,NULL,
  '{}'::jsonb,NULL,NULL,'{}','ninguno',NULL),
 ('b0000000-0000-4000-8000-000000000011','Fuente Sin Id','regular','american',
  'a0000000-0000-4000-8000-000000000001',2020,NULL,NULL,'ongoing',NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL,
  '{}'::jsonb,'comic_vine',NULL,'{}','ninguno',NULL),
 ('b0000000-0000-4000-8000-000000000012','Ids Sin Intento','regular','american',
  'a0000000-0000-4000-8000-000000000001',2020,NULL,NULL,'ongoing',555,NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL,
  '{}'::jsonb,NULL,NULL,'{}','ninguno',NULL),
 ('b0000000-0000-4000-8000-000000000013','Asociacion Rara','regular','american',
  'a0000000-0000-4000-8000-000000000001',2020,NULL,NULL,'ongoing',666,NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL,
  '{"asociaciones":[{"version":1,"fuente":"comic_vine","id_externo":"999","entidad":"serie","kind":null,"fecha":"2026-11-01T00:00:00+00:00","operacion_id":"c0000000-0000-4000-8000-000000000001","origen":"confirmada","modo":"busqueda"},{"version":1,"fuente":"comic_vine","id_externo":"667","entidad":"serie","kind":null,"fecha":"2026-11-02T00:00:00+00:00","operacion_id":"c0000000-0000-4000-8000-000000000002","origen":"confirmada","modo":"busqueda"}]}'::jsonb,
  NULL,NULL,'{}','ninguno',NULL),
 ('b0000000-0000-4000-8000-000000000014','Bloqueos','regular','american',
  'a0000000-0000-4000-8000-000000000001',2020,NULL,NULL,'ongoing',NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL,
  '{}'::jsonb,NULL,NULL,'{"titulo_inexistente"}','ninguno',NULL),
 ('b0000000-0000-4000-8000-000000000015','Años Raros','regular','american',
  'a0000000-0000-4000-8000-000000000001',1800,NULL,NULL,'ongoing',NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL,
  '{}'::jsonb,NULL,NULL,'{}','ninguno',NULL),
 ('b0000000-0000-4000-8000-000000000016','Ciclo A','regular','american',
  'a0000000-0000-4000-8000-000000000001',2020,NULL,NULL,'ongoing',NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL,
  '{}'::jsonb,NULL,NULL,'{}','ninguno',NULL),
 ('b0000000-0000-4000-8000-000000000017','Ciclo B','regular','american',
  'a0000000-0000-4000-8000-000000000001',2020,NULL,NULL,'ongoing',NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL,
  '{}'::jsonb,NULL,NULL,'{}','ninguno',NULL),
 ('b0000000-0000-4000-8000-000000000018','Tebeosfera Americana','regular','american',
  'a0000000-0000-4000-8000-000000000001',2020,NULL,NULL,'ongoing',NULL,NULL,'slug-tebeosfera',NULL,NULL,NULL,NULL,NULL,NULL,
  '{}'::jsonb,NULL,NULL,'{}','ninguno',NULL),
 ('b0000000-0000-4000-8000-000000000019','Padre One Shot','one_shot','other',
  'a0000000-0000-4000-8000-000000000005',2020,NULL,NULL,'ongoing',NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL,
  '{}'::jsonb,NULL,NULL,'{}','ninguno',NULL),
 ('b0000000-0000-4000-8000-000000000020','Hijo','regular','other',
  'a0000000-0000-4000-8000-000000000005',2020,NULL,NULL,'ongoing',NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL,
  '{}'::jsonb,NULL,NULL,'{}','ninguno','b0000000-0000-4000-8000-000000000019'),
 ('b0000000-0000-4000-8000-000000000021','Titulo  Sucio ','regular','american',
  'a0000000-0000-4000-8000-000000000001',2020,NULL,NULL,'ongoing',NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL,
  '{}'::jsonb,NULL,NULL,'{}','ninguno',NULL),
 ('b0000000-0000-4000-8000-000000000022','Alias Local','regular','american',
  'a0000000-0000-4000-8000-000000000001',2020,NULL,NULL,'ongoing',NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL,
  '{}'::jsonb,NULL,NULL,'{}','ninguno',NULL),
 ('b0000000-0000-4000-8000-000000000023','Alias Importado','regular','american',
  'a0000000-0000-4000-8000-000000000001',2020,NULL,NULL,'ongoing',NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL,
  '{}'::jsonb,NULL,NULL,'{}','ninguno',NULL),
 ('b0000000-0000-4000-8000-000000000024','Sin Archivos','regular','american',
  'a0000000-0000-4000-8000-000000000001',2020,NULL,NULL,'ongoing',NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL,
  '{}'::jsonb,NULL,NULL,'{}','ninguno',NULL);

UPDATE series SET parent_series_id='b0000000-0000-4000-8000-000000000017'
 WHERE id='b0000000-0000-4000-8000-000000000016';
UPDATE series SET parent_series_id='b0000000-0000-4000-8000-000000000016'
 WHERE id='b0000000-0000-4000-8000-000000000017';

INSERT INTO issues (id, series_id, issue_number, volume, title, release_date, format, page_count,
                    comic_vine_id, metadata, metadata_source, locked_fields)
VALUES
 ('d0000000-0000-4000-8000-000000000001','b0000000-0000-4000-8000-000000000001','1',1,'Uno',NULL,'single_issue',20,9001,'{}'::jsonb,'comic_vine','{}'),
 ('d0000000-0000-4000-8000-000000000002','b0000000-0000-4000-8000-000000000001','2',NULL,'Dos',NULL,'single_issue',20,NULL,'{}'::jsonb,NULL,'{}'),
 ('d0000000-0000-4000-8000-000000000003','b0000000-0000-4000-8000-000000000001','2',NULL,'Dos bis',NULL,'single_issue',20,NULL,'{}'::jsonb,NULL,'{}'),
 ('d0000000-0000-4000-8000-000000000004','b0000000-0000-4000-8000-000000000001','51',1,'Fuera',NULL,'single_issue',20,NULL,'{}'::jsonb,NULL,'{}'),
 ('d0000000-0000-4000-8000-000000000005','b0000000-0000-4000-8000-000000000001','Annual 1',1,'Anual',NULL,'single_issue',20,NULL,'{}'::jsonb,NULL,'{}'),
 ('d0000000-0000-4000-8000-000000000006','b0000000-0000-4000-8000-000000000001','1.5',1,'Decimal',NULL,'single_issue',20,NULL,'{}'::jsonb,NULL,'{}'),
 ('d0000000-0000-4000-8000-000000000007','b0000000-0000-4000-8000-000000000001',' 12',1,'Espacios',NULL,'single_issue',20,NULL,'{}'::jsonb,NULL,'{}'),
 ('d0000000-0000-4000-8000-000000000008','b0000000-0000-4000-8000-000000000001','5',1,'B5b',NULL,'single_issue',20,9005,'{}'::jsonb,'comic_vine','{}'),
 ('d0000000-0000-4000-8000-000000000009','b0000000-0000-4000-8000-000000000005','1',1,'Mortadelo 1',NULL,'single_issue',20,NULL,'{}'::jsonb,NULL,'{}'),
 ('d0000000-0000-4000-8000-000000000010','b0000000-0000-4000-8000-000000000006','1',1,'Obra 1',NULL,'single_issue',20,NULL,'{}'::jsonb,NULL,'{}'),
 ('d0000000-0000-4000-8000-000000000011','b0000000-0000-4000-8000-000000000006','2',1,'Obra 2',NULL,'single_issue',20,NULL,'{}'::jsonb,NULL,'{}'),
 ('d0000000-0000-4000-8000-000000000012','b0000000-0000-4000-8000-000000000009','1',1,'Corta',NULL,'single_issue',20,NULL,'{}'::jsonb,NULL,'{}'),
 ('d0000000-0000-4000-8000-000000000013','b0000000-0000-4000-8000-000000000003','3',1,'B5a',NULL,'single_issue',20,9100,'{}'::jsonb,NULL,'{}'),
 ('d0000000-0000-4000-8000-000000000014','b0000000-0000-4000-8000-000000000003','',1,'Vacío',NULL,'single_issue',20,NULL,'{}'::jsonb,NULL,'{}'),
 ('d0000000-0000-4000-8000-000000000015','b0000000-0000-4000-8000-000000000003','007',1,'Ceros',NULL,'single_issue',20,NULL,'{}'::jsonb,NULL,'{}'),
 ('d0000000-0000-4000-8000-000000000016','b0000000-0000-4000-8000-000000000002','4',1,'Fecha',DATE '1900-01-01','single_issue',20,NULL,'{}'::jsonb,NULL,'{}'),
 ('d0000000-0000-4000-8000-000000000017','b0000000-0000-4000-8000-000000000002','5',1,'Mojibake',NULL,'single_issue',20,NULL,'{}'::jsonb,NULL,'{}'),
 ('d0000000-0000-4000-8000-000000000018','b0000000-0000-4000-8000-000000000009','2',1,'Sin archivos',NULL,'single_issue',20,NULL,'{}'::jsonb,NULL,'{}');

UPDATE issues SET synopsis='Sinopsis con &amp; y <b>marcado</b>'
 WHERE id='d0000000-0000-4000-8000-000000000001';
UPDATE issues SET synopsis='Texto con Ã± roto'
 WHERE id='d0000000-0000-4000-8000-000000000017';

INSERT INTO files (id, issue_id, file_path, root_id, file_name, file_format, file_size_bytes,
                   sha256_hash, original_sha256, covered_issue_ids, metadata, is_missing,
                   missing_since, review_dismissed, metadata_source)
VALUES
 ('e0000000-0000-4000-8000-000000000001','d0000000-0000-4000-8000-000000000001',
  (SELECT path FROM _root) || '/x1.cbz',(SELECT id FROM _root),'Batman 002.cbz','cbz',10,
  repeat('b',64),NULL,'{}'::uuid[],
  '{"match_status":"auto","formato_contenido":{"firma":"zip","clase":"tebeo"},"discrepancias":[{"version":1,"clave":"k1","origen":"rescan","estado":"pendiente","observada_en":"2026-01-01T00:00:00+00:00"}]}'::jsonb,
  false,NULL,false,NULL),
 ('e0000000-0000-4000-8000-000000000002','d0000000-0000-4000-8000-000000000004',
  (SELECT path FROM _root) || '/x2.cbz',(SELECT id FROM _root),'Batman 051.cbz','cbz',10,
  repeat('b',64),NULL,'{}'::uuid[],'{"match_status":"auto"}'::jsonb,false,NULL,false,NULL),
 ('e0000000-0000-4000-8000-000000000003','d0000000-0000-4000-8000-000000000001',
  (SELECT path FROM _root) || '/x3.cbz',(SELECT id FROM _root),'Batman 001.cbz','cbz',10,
  repeat('b',64),NULL,'{}'::uuid[],'{"match_status":"auto"}'::jsonb,false,NULL,false,NULL),
 ('e0000000-0000-4000-8000-000000000004','d0000000-0000-4000-8000-000000000001',
  (SELECT path FROM _root) || '/x4.cbz',(SELECT id FROM _root),'Batman 004.cbz','cbz',10,
  repeat('c',64),NULL,ARRAY['d0000000-0000-4000-8000-000000000001','f0000000-0000-4000-8000-000000000001']::uuid[],
  '{"match_status":"auto","vinculo_historial":[{"serie_id":"ffffffff-0000-4000-8000-000000000001","issue_id":"ffffffff-0000-4000-8000-000000000002","deshecho":{"operacion_id":"ffffffff-0000-4000-8000-000000000003","fecha":"2026-01-01T00:00:00+00:00"}}]}'::jsonb,
  false,NULL,false,NULL),
 ('e0000000-0000-4000-8000-000000000005','d0000000-0000-4000-8000-000000000004',
  (SELECT path FROM _root) || '/x5.cbz',(SELECT id FROM _root),'Batman 005.cbz','cbz',10,
  repeat('d',64),NULL,ARRAY['d0000000-0000-4000-8000-000000000001']::uuid[],
  '{"match_status":"auto"}'::jsonb,false,NULL,false,NULL),
 ('e0000000-0000-4000-8000-000000000006','d0000000-0000-4000-8000-000000000006',
  (SELECT path FROM _root) || '/x6.cbz',(SELECT id FROM _root),'Batman x6.cbz','cbz',10,
  repeat('e',64),NULL,'{}'::uuid[],'{"match_status":"auto"}'::jsonb,true,NULL,false,NULL),
 ('e0000000-0000-4000-8000-000000000007',NULL,'/otro/f7.cbz',(SELECT id FROM _root),
  'f7.cbz','cbz',10,NULL,NULL,'{}'::uuid[],'{}'::jsonb,false,NULL,false,NULL),
 ('e0000000-0000-4000-8000-000000000008',NULL,(SELECT path FROM _root) || '/sub/f8.cbz',NULL,
  'f8.cbz','cbz',10,NULL,NULL,'{}'::uuid[],'{}'::jsonb,false,NULL,false,NULL),
 ('e0000000-0000-4000-8000-000000000009','d0000000-0000-4000-8000-000000000009',
  (SELECT path FROM _root) || '/x9.cbz',(SELECT id FROM _root),'Mortadelo 002.cbz','cbz',10,
  repeat('f',64),NULL,'{}'::uuid[],
  '{"match_status":"auto","formato_contenido":{"firma":"rar","clase":"tebeo"}}'::jsonb,
  false,NULL,false,NULL),
 ('e0000000-0000-4000-8000-000000000010',NULL,(SELECT path FROM _root) || '/x10.cbz',(SELECT id FROM _root),
  'x10.cbz','cbz',10,NULL,NULL,'{}'::uuid[],'{"match_status":"matched"}'::jsonb,false,NULL,false,NULL),
 ('e0000000-0000-4000-8000-000000000011','d0000000-0000-4000-8000-000000000001',
  (SELECT path FROM _root) || '/x11.cbz',(SELECT id FROM _root),'Batman 011.cbz','cbz',10,
  repeat('g',64),NULL,'{}'::uuid[],'{"match_status":"unsorted"}'::jsonb,false,NULL,false,NULL),
 ('e0000000-0000-4000-8000-000000000012','d0000000-0000-4000-8000-000000000012',
  '/media/off/f12.cbz','a0000000-0000-4000-8000-000000000009','f12.cbz','cbz',10,
  repeat('h',64),NULL,'{}'::uuid[],'{"match_status":"auto"}'::jsonb,false,NULL,false,NULL),
 ('e0000000-0000-4000-8000-000000000013','d0000000-0000-4000-8000-000000000001',
  (SELECT path FROM _root) || '/decl_folder/f13.cbz',(SELECT id FROM _root),'f13.cbz','cbz',10,
  repeat('i',64),NULL,'{}'::uuid[],'{"match_status":"auto"}'::jsonb,false,NULL,false,NULL),
 ('e0000000-0000-4000-8000-000000000014','d0000000-0000-4000-8000-000000000009',
  (SELECT path FROM _root) || '/x14.cbz',(SELECT id FROM _root),'Mortadelo 001.cbz','cbz',10,
  repeat('j',64),NULL,'{}'::uuid[],'{"match_status":"auto"}'::jsonb,false,NULL,false,NULL);

INSERT INTO wishlist (id, series_id, issue_id, status, origen, numero) VALUES
 ('f1000000-0000-4000-8000-000000000001','b0000000-0000-4000-8000-000000000005','d0000000-0000-4000-8000-000000000004','wanted','manual',NULL),
 ('f1000000-0000-4000-8000-000000000002',NULL,'d0000000-0000-4000-8000-000000000001','wanted','manual',NULL),
 ('f1000000-0000-4000-8000-000000000003','b0000000-0000-4000-8000-000000000005',NULL,'wanted','politica',999),
 ('f1000000-0000-4000-8000-000000000004','b0000000-0000-4000-8000-000000000005',NULL,'wanted','politica',1);

INSERT INTO reading_progress (id, issue_id, status, current_page, file_id, started_at, completed_at) VALUES
 ('f2000000-0000-4000-8000-000000000001','d0000000-0000-4000-8000-000000000001','reading',99,'e0000000-0000-4000-8000-000000000002',NULL,NULL),
 ('f2000000-0000-4000-8000-000000000002','d0000000-0000-4000-8000-000000000012','completed',3,NULL,NULL,NULL),
 ('f2000000-0000-4000-8000-000000000003','d0000000-0000-4000-8000-000000000018','reading',1,NULL,'2026-01-02T00:00:00+00:00','2026-01-01T00:00:00+00:00'),
 ('f2000000-0000-4000-8000-000000000004','d0000000-0000-4000-8000-000000000005','reading',1,NULL,NULL,NULL);

INSERT INTO collections (id, name, cover_series_id) VALUES
 ('f3000000-0000-4000-8000-000000000001','Vacía',NULL),
 ('f3000000-0000-4000-8000-000000000002','Con portada', 'b0000000-0000-4000-8000-000000000002');
INSERT INTO collection_series (collection_id, series_id) VALUES
 ('f3000000-0000-4000-8000-000000000002','b0000000-0000-4000-8000-000000000001');

INSERT INTO story_arcs (id, title) VALUES ('f4000000-0000-4000-8000-000000000001','Saga');
INSERT INTO story_arc_issues (story_arc_id, issue_id, reading_order) VALUES
 ('f4000000-0000-4000-8000-000000000001','d0000000-0000-4000-8000-000000000001',1),
 ('f4000000-0000-4000-8000-000000000001','d0000000-0000-4000-8000-000000000002',1),
 ('f4000000-0000-4000-8000-000000000001','d0000000-0000-4000-8000-000000000004',3);

INSERT INTO upgrade_proposals (id, issue_id, file_id, candidate_title, candidate_indexer,
                               candidate_url, status, created_at)
VALUES ('f5000000-0000-4000-8000-000000000001','d0000000-0000-4000-8000-000000000001',
        'e0000000-0000-4000-8000-000000000002','Mejor','idx','https://example.invalid/x',
        'pendiente', now() - interval '40 days');

INSERT INTO import_runs (id, started_at, finished_at, details)
VALUES ('f6000000-0000-4000-8000-000000000001', now() - interval '1 day',
        now() - interval '1 day', '{"comprobacion_biblioteca":{"ambito":"biblioteca","resultado":"raiz_inaccesible","archivos_registrados":14,"ausentes":null,"bajas_omitidas":true,"fecha":"2026-11-19T00:00:00+00:00"}}'::jsonb);

INSERT INTO entity_source_records (id, entity_type, entity_id, source, external_id, payload, fetched_at)
VALUES
 ('f7000000-0000-4000-8000-000000000001','series','b0000000-0000-4000-8000-000000000001','comic_vine','111',
  '{"normalizado":{"edition_scope":{"title":"Batman","start_year":1940,"total_issues":50}}}'::jsonb,now()),
 ('f7000000-0000-4000-8000-000000000002','series','b0000000-0000-4000-8000-000000000001','comic_vine','112',
  '{"normalizado":{"edition_scope":{"title":"Batman","start_year":1941,"total_issues":60}}}'::jsonb,now()),
 ('f7000000-0000-4000-8000-000000000003','series','b0000000-0000-4000-8000-000000000002','comic_vine','222',
  '{"normalizado":{"edition_scope":{"title":"Superman","start_year":2011}}}'::jsonb,now()),
 ('f7000000-0000-4000-8000-000000000004','series','b0000000-0000-4000-8000-000000000002','anilist','777',
  '{"normalizado":{"edition_scope":{"title":"Superman","start_year":1980}}}'::jsonb,now()),
 ('f7000000-0000-4000-8000-000000000005','series','b0000000-0000-4000-8000-000000000005','comic_vine','333',
  '{"normalizado":{"edition_scope":{"title":"Mortadelo","start_year":1958,"total_issues":20}}}'::jsonb,now()),
 ('f7000000-0000-4000-8000-000000000006','issue','d0000000-0000-4000-8000-000000000008','comic_vine','9005',
  '{"raw_acotado":{"id":9005,"issue_number":"6"}}'::jsonb,now()),
 ('f7000000-0000-4000-8000-000000000007','series','b0000000-0000-4000-8000-000000000010','fandom_dc','batman_vol_1',
  '{"normalizado":{"edition_scope":{"title":"Fandom Mal","start_year":2020}}}'::jsonb,now());

INSERT INTO field_provenance (entity_type, entity_id, field, source, value, fetched_at, locked)
VALUES ('series','b0000000-0000-4000-8000-000000000001','total_issues','comic_vine','999'::jsonb,now(),false);

INSERT INTO local_aliases (id, pattern_norm, series_id, origen, estado, version, scope_path, historial)
VALUES ('f8000000-0000-4000-8000-000000000001','patron','b0000000-0000-4000-8000-000000000022',
        'manual','activo',1,NULL,'[]'::jsonb);
INSERT INTO alias_importado (id, alias_id, version, patron_norm, scope_path, series_id, origen,
                             estado, vigente_desde, procedencia)
VALUES ('f8000000-0000-4000-8000-000000000002','f8000000-0000-4000-8000-000000000003',1,'patron',NULL,
        'b0000000-0000-4000-8000-000000000023','importado','activo',now(),'{}'::jsonb);

INSERT INTO declaraciones_carpeta (id, declaracion_id, version, contexto_raiz, incluir_descendientes,
                                   tipo_de_significado, origen, estado, vigente_desde)
VALUES ('f9000000-0000-4000-8000-000000000001','f9000000-0000-4000-8000-000000000001',1,
        'decl_folder',true,'publicacion','local','activa',now());
INSERT INTO correspondencias_contexto (id, correspondencia_id, version, declaracion_version_id,
                                       contexto_raiz, incluir_descendientes, destino_tipo,
                                       destino_id, origen, estado, vigente_desde, procedencia)
VALUES ('f9000000-0000-4000-8000-000000000002','f9000000-0000-4000-8000-000000000002',1,
        'f9000000-0000-4000-8000-000000000001','decl_folder',true,'serie',
        'b0000000-0000-4000-8000-000000000009','local','activa',now(),'{}'::jsonb);

INSERT INTO asignacion_operaciones (id, file_id, series_id, estado, origen, destino, temporal,
                                    size_bytes, mtime_ns, sha256, issue_number, formato, creada,
                                    actualizada)
VALUES ('fa000000-0000-4000-8000-000000000001','e0000000-0000-4000-8000-000000000001',
        'b0000000-0000-4000-8000-000000000001','preparada','/origen/a.cbz','/destino/a.cbz',
        '/temporal/a.cbz',10,1,repeat('a',64),'1','single_issue',
        now() - interval '3 days', now() - interval '2 days');

INSERT INTO paquete_operaciones (id, paquete_clave, paquete_path, paquete_dev, paquete_ino,
                                 paquete_size, paquete_mtime_ns, firma, estado, creada,
                                 actualizada)
VALUES ('fa000000-0000-4000-8000-000000000002','p1','/tmp/p1',1,1,10,1,'zip','extrayendo',
        now() - interval '3 days', now() - interval '2 days');

INSERT INTO apartado_operaciones (id, estado, token_hasta, creada, actualizada,
                                  total_grupos, total_archivos, total_bytes)
VALUES ('fa000000-0000-4000-8000-000000000003','en_curso',now() + interval '1 hour',
        now() - interval '3 days', now() - interval '2 days',1,1,10);

-- `creators.name_norm` tiene un UNIQUE en la migración (`uq_creators_name_norm`):
-- G2c no puede tener caso por construcción; se deja un creador con un campo
-- bloqueado inexistente para F5.
INSERT INTO creators (id, name, locked_fields) VALUES
 ('fb000000-0000-4000-8000-000000000001','José','{"campo_que_no_existe"}');
INSERT INTO characters (id, name, locked_fields) VALUES
 ('fb000000-0000-4000-8000-000000000003','Clark Kent','{"campo_que_no_existe"}');

-- Casos añadidos para cubrir las comprobaciones que el primer lote no tocaba.
INSERT INTO series (id, title, kind, tradition, publisher_id, start_year, end_year, total_issues,
                    status, comic_vine_id, anilist_id, tebeosfera_slug, gcd_id, metron_id,
                    open_library_id, fandom_dc_slug, fandom_marvel_slug, cover_url,
                    metadata, metadata_source, enrichment_attempted_at, locked_fields,
                    wishlist_policy, parent_series_id, language)
VALUES
 ('b0000000-0000-4000-8000-000000000025','Titulo Real','regular','american',
  'a0000000-0000-4000-8000-000000000001',2020,NULL,NULL,'ongoing',888,NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL,
  '{}'::jsonb,'comic_vine',now(),'{}','ninguno',NULL,NULL),
 ('b0000000-0000-4000-8000-000000000026','Manga Mal','regular','american',
  'a0000000-0000-4000-8000-000000000001',2020,NULL,NULL,'ongoing',NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL,
  '{}'::jsonb,NULL,NULL,'{}','ninguno',NULL,'ja'),
 ('b0000000-0000-4000-8000-000000000027','No Completar','regular','american',
  'a0000000-0000-4000-8000-000000000001',2020,NULL,NULL,'ongoing',NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL,
  '{"coleccion":{"no_completar":true,"version":1}}'::jsonb,NULL,NULL,'{}','faltantes',NULL,NULL),
 ('b0000000-0000-4000-8000-000000000028','Album','regular','franco_belgian',
  'a0000000-0000-4000-8000-000000000005',2020,NULL,NULL,'ongoing',12345,NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL,
  '{}'::jsonb,NULL,NULL,'{}','ninguno',NULL,NULL),
 ('b0000000-0000-4000-8000-000000000029','Sin Evidencia','regular','american',
  'a0000000-0000-4000-8000-000000000001',NULL,NULL,NULL,'ongoing',7777,NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL,
  '{}'::jsonb,NULL,NULL,'{}','ninguno',NULL,NULL);

UPDATE issues SET series_id='b0000000-0000-4000-8000-000000000024'
 WHERE id='d0000000-0000-4000-8000-000000000018';

INSERT INTO entity_source_records (id, entity_type, entity_id, source, external_id, payload, fetched_at)
VALUES ('f7000000-0000-4000-8000-000000000008','series','b0000000-0000-4000-8000-000000000025','comic_vine','888',
        '{"normalizado":{"edition_scope":{"title":"Otro Titulo","start_year":2020}}}'::jsonb, now());

INSERT INTO files (id, issue_id, file_path, root_id, file_name, file_format, file_size_bytes,
                   sha256_hash, original_sha256, covered_issue_ids, metadata, is_missing,
                   missing_since, review_dismissed, metadata_source)
VALUES
 ('e0000000-0000-4000-8000-000000000015',NULL,(SELECT path FROM _root) || '/case.cbz',(SELECT id FROM _root),
  'case.cbz','cbz',10,NULL,NULL,'{}'::uuid[],'{}'::jsonb,false,NULL,false,NULL),
 ('e0000000-0000-4000-8000-000000000016',NULL,(SELECT path FROM _root) || '/CASE.cbz',(SELECT id FROM _root),
  'CASE.cbz','cbz',10,NULL,NULL,'{}'::uuid[],'{}'::jsonb,false,NULL,false,NULL),
 ('e0000000-0000-4000-8000-000000000017','d0000000-0000-4000-8000-000000000001',
  (SELECT path FROM _root) || '/x17.cbz',(SELECT id FROM _root),'Batman 017.cbz','cbz',10,
  repeat('l',64),NULL,'{}'::uuid[],'{"match_status":"auto","edicion":"omnigold"}'::jsonb,
  false,NULL,false,NULL),
 ('e0000000-0000-4000-8000-000000000018','d0000000-0000-4000-8000-000000000001',
  (SELECT path FROM _root) || '/x18.cbz',(SELECT id FROM _root),'Batman 018.cbz','cbz',10,
  repeat('m',64),NULL,ARRAY['d0000000-0000-4000-8000-000000000001','d0000000-0000-4000-8000-000000000012']::uuid[],
  '{"match_status":"auto"}'::jsonb,false,NULL,false,NULL),
 ('e0000000-0000-4000-8000-000000000019','d0000000-0000-4000-8000-000000000001',
  (SELECT path FROM _root) || '/x19.cbz',(SELECT id FROM _root),'Batman 019.cbz','cbz',10,
  repeat('n',64),NULL,'{}'::uuid[],'{"match_status":"auto"}'::jsonb,false,NULL,false,NULL),
 ('e0000000-0000-4000-8000-000000000020','d0000000-0000-4000-8000-000000000001',
  (SELECT path FROM _root) || '/x20.cbz',(SELECT id FROM _root),'Batman 020.cbz','cbz',10,
  repeat('n',64),NULL,'{}'::uuid[],'{"match_status":"auto"}'::jsonb,false,NULL,false,NULL);

COMMIT;
