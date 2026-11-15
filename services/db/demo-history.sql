-- M4-01: two weeks of demo history so the clinician dashboard has data on a fresh stack.
-- Runs once, on an empty volume, after seed.sh. Only Bri and Casey get history: Alex stays
-- empty so the dashboard's empty state shows, and so the Compose chat test owns Alex's rows.
-- Messages are placeholders. No real or crisis wording is stored, and the clinician API
-- never returns message text anyway.

DO $$
DECLARE
    ada   CONSTANT uuid := '00000000-0000-0000-0000-000000000101';
    bri   CONSTANT uuid := '00000000-0000-0000-0000-000000000202';
    casey CONSTANT uuid := '00000000-0000-0000-0000-000000000203';
    -- Bri: lighter early on, heavier in the middle, a crisis three days ago (not yet reviewed).
    bri_days  int[]  := ARRAY[13, 11, 9, 6, 3, 1];
    bri_text  text[] := ARRAY['joy', 'neutral', 'sadness', 'fear', 'sadness', 'neutral'];
    -- Casey: steady, camera off, one older flag that Dr. Ada already reviewed.
    casey_days int[]  := ARRAY[12, 8, 5, 2];
    casey_text text[] := ARRAY['neutral', 'joy', 'neutral', 'joy'];
    k int;
    i int;
    started timestamptz;
    s uuid;
    m uuid;
    label text;
    second text;
    p numeric;
BEGIN
    FOR k IN 1 .. array_length(bri_days, 1) LOOP
        started := date_trunc('hour', now()) - make_interval(days => bri_days[k], hours => 2);
        INSERT INTO sessions (patient_id, started_at, ended_at, camera_consent)
        VALUES (bri, started, started + interval '18 minutes', true)
        RETURNING id INTO s;
        FOR i IN 0 .. 3 LOOP
            label := CASE WHEN i = 3 THEN 'neutral' ELSE bri_text[k] END;
            second := CASE WHEN label = 'neutral' THEN 'joy' ELSE 'neutral' END;
            p := 0.55 + 0.1 * (i % 2);
            INSERT INTO messages (session_id, role, text, created_at)
            VALUES (s, 'patient', '(seeded demo message)', started + make_interval(mins => i * 4));
            INSERT INTO emotion_windows (session_id, ts, visual_status, visual_top2, text_top2, tone_mode)
            VALUES (
                s,
                started + make_interval(mins => i * 4),
                (CASE i WHEN 1 THEN 'uncertain' WHEN 3 THEN 'dropped' ELSE 'ok' END)::visual_status,
                CASE WHEN i IN (0, 2) THEN jsonb_build_array(
                    jsonb_build_array(CASE bri_text[k] WHEN 'joy' THEN 'happy' ELSE 'neutral' END, 0.6),
                    jsonb_build_array('sad', 0.2))
                END,
                jsonb_build_array(jsonb_build_array(label, p), jsonb_build_array(second, 0.2)),
                'supportive'
            );
        END LOOP;
        IF bri_days[k] = 3 THEN
            INSERT INTO messages (session_id, role, text, created_at, safety_hit)
            VALUES (s, 'patient', '(seeded demo message: crisis rule matched)', started + interval '16 minutes', true)
            RETURNING id INTO m;
            INSERT INTO review_flags (patient_id, message_id, created_at)
            VALUES (bri, m, started + interval '16 minutes');
        END IF;
    END LOOP;

    FOR k IN 1 .. array_length(casey_days, 1) LOOP
        started := date_trunc('hour', now()) - make_interval(days => casey_days[k], hours => 5);
        INSERT INTO sessions (patient_id, started_at, ended_at, camera_consent)
        VALUES (casey, started, started + interval '12 minutes', false)
        RETURNING id INTO s;
        FOR i IN 0 .. 2 LOOP
            label := casey_text[k];
            second := CASE WHEN label = 'neutral' THEN 'joy' ELSE 'neutral' END;
            INSERT INTO messages (session_id, role, text, created_at)
            VALUES (s, 'patient', '(seeded demo message)', started + make_interval(mins => i * 4));
            INSERT INTO emotion_windows (session_id, ts, visual_status, visual_top2, text_top2, tone_mode)
            VALUES (
                s,
                started + make_interval(mins => i * 4),
                'camera_off',
                NULL,
                jsonb_build_array(jsonb_build_array(label, 0.7), jsonb_build_array(second, 0.2)),
                CASE WHEN i = 2 THEN 'coach' ELSE 'supportive' END::tone_mode
            );
        END LOOP;
        IF casey_days[k] = 8 THEN
            INSERT INTO messages (session_id, role, text, created_at, safety_hit)
            VALUES (s, 'patient', '(seeded demo message: crisis rule matched)', started + interval '10 minutes', true)
            RETURNING id INTO m;
            INSERT INTO review_flags (patient_id, message_id, created_at, reviewed_at, reviewed_by)
            VALUES (casey, m, started + interval '10 minutes', started + interval '1 day', ada);
        END IF;
    END LOOP;
END
$$;
