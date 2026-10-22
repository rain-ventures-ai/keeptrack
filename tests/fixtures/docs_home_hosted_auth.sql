-- Supplemental real-DB check after keeptrack-cloud tests/db/00_seed.sql and 01_schema.sql.
-- Synthetic data only; the entire destination mutation is rolled back.
BEGIN;
SET LOCAL ROLE kt_api;
SELECT set_config('request.jwt.claim.sub','10000000-0000-4000-8000-000000000001',true);
DO $$ DECLARE b uuid := '30000000-0000-4000-8000-000000000001'; f jsonb; body jsonb; r jsonb; request jsonb; BEGIN
 f := kt.read_file(b,'tasks.json');
 body := f->'body' || jsonb_build_object('settings', coalesce(f#>'{body,settings}','{}') || jsonb_build_object('docs_home',jsonb_build_object('provider','google-drive','root','https://drive.google.com/drive/folders/synthetic-docs-root')));
 request := jsonb_build_object('ops',jsonb_build_array(jsonb_build_object('kind','put','path','tasks.json','baseRev',f->>'rev','body',body)));
 r := kt.commit_files(b,gen_random_uuid(),sha256('docs-owner'::bytea),request);
 PERFORM test.ok(EXISTS(SELECT 1 FROM jsonb_array_elements(r->'files') x WHERE x#>>'{body,settings,docs_home,provider}'='google-drive'),'docs-home real DB: human owner may set unknown shared setting');
 f := kt.read_file(b,'tasks.json');
 body := jsonb_set(f->'body','{settings,docs_home,root}','"https://drive.google.com/drive/folders/replacement"');
 request := jsonb_build_object('ops',jsonb_build_array(jsonb_build_object('kind','put','path','tasks.json','baseRev',f->>'rev','body',body)));
 PERFORM set_config('request.jwt.claim.sub','10000000-0000-4000-8000-000000000002',true);
 PERFORM test.raises(format('SELECT kt.commit_files(%L,gen_random_uuid(),sha256(''docs-editor''::bytea),%L)',b,request),'forbidden','docs-home real DB: editor destination change refused');
 PERFORM kt.authenticate_cli('70000000-0000-4000-8000-000000000001',decode(repeat('11',32),'hex'));
 PERFORM test.raises(format('SELECT kt.commit_files(%L,gen_random_uuid(),sha256(''docs-agent''::bytea),%L)',b,request),'invalid_fence','docs-home real DB: agent root write refused');
 PERFORM test.ok(kt.read_file(b,'tasks.json')#>>'{body,settings,docs_home,root}'='https://drive.google.com/drive/folders/synthetic-docs-root','docs-home real DB: refusals leave destination unchanged');
END $$;
ROLLBACK;
