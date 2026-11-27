CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TYPE user_role AS ENUM ('patient', 'clinician');
CREATE TYPE message_role AS ENUM ('patient', 'assistant', 'system');
CREATE TYPE visual_status AS ENUM ('ok', 'uncertain', 'dropped', 'camera_off');
CREATE TYPE tone_mode AS ENUM ('coach', 'supportive');
-- Why a message was flagged for the clinician: the crisis check, or a long session (M4-16).
CREATE TYPE review_reason AS ENUM ('crisis', 'long_session');

CREATE TABLE users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email TEXT NOT NULL UNIQUE,
    display_name TEXT NOT NULL,
    role user_role NOT NULL,
    password_hash TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE patients (
    user_id UUID PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
    clinician_id UUID NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    CONSTRAINT patient_cannot_be_own_clinician CHECK (user_id <> clinician_id)
);

CREATE TABLE sessions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    patient_id UUID NOT NULL REFERENCES patients(user_id) ON DELETE CASCADE,
    started_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    ended_at TIMESTAMPTZ,
    camera_consent BOOLEAN NOT NULL,
    CONSTRAINT session_end_after_start CHECK (ended_at IS NULL OR ended_at >= started_at)
);

CREATE TABLE messages (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id UUID NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    role message_role NOT NULL,
    text TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    safety_hit BOOLEAN NOT NULL DEFAULT FALSE
);

CREATE TABLE emotion_windows (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id UUID NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    ts TIMESTAMPTZ NOT NULL DEFAULT now(),
    visual_status visual_status NOT NULL,
    visual_top2 JSONB,
    text_top2 JSONB,
    tone_mode tone_mode NOT NULL,
    CONSTRAINT visual_top2_is_array CHECK (visual_top2 IS NULL OR jsonb_typeof(visual_top2) = 'array'),
    CONSTRAINT text_top2_is_array CHECK (text_top2 IS NULL OR jsonb_typeof(text_top2) = 'array')
);

CREATE TABLE review_flags (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    patient_id UUID NOT NULL REFERENCES patients(user_id) ON DELETE CASCADE,
    message_id UUID NOT NULL REFERENCES messages(id) ON DELETE RESTRICT,
    reason review_reason NOT NULL DEFAULT 'crisis',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    reviewed_at TIMESTAMPTZ,
    reviewed_by UUID REFERENCES users(id) ON DELETE SET NULL,
    CONSTRAINT review_state_is_complete_or_empty CHECK (
        (reviewed_at IS NULL AND reviewed_by IS NULL)
        OR (reviewed_at IS NOT NULL AND reviewed_by IS NOT NULL)
    )
);

CREATE FUNCTION enforce_patient_assignment_roles()
RETURNS TRIGGER AS $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM users WHERE id = NEW.user_id AND role = 'patient') THEN
        RAISE EXCEPTION 'patients.user_id must reference a user with role patient';
    END IF;

    IF NOT EXISTS (SELECT 1 FROM users WHERE id = NEW.clinician_id AND role = 'clinician') THEN
        RAISE EXCEPTION 'patients.clinician_id must reference a user with role clinician';
    END IF;

    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER patients_require_patient_and_clinician_roles
BEFORE INSERT OR UPDATE OF user_id, clinician_id ON patients
FOR EACH ROW EXECUTE FUNCTION enforce_patient_assignment_roles();

CREATE FUNCTION enforce_review_flag_relationships()
RETURNS TRIGGER AS $$
DECLARE
    message_patient_id UUID;
    reviewer_role user_role;
BEGIN
    SELECT sessions.patient_id INTO message_patient_id
    FROM messages
    JOIN sessions ON sessions.id = messages.session_id
    WHERE messages.id = NEW.message_id;

    IF message_patient_id IS NULL OR message_patient_id <> NEW.patient_id THEN
        RAISE EXCEPTION 'review_flags.message_id must belong to a session for review_flags.patient_id';
    END IF;

    IF NEW.reviewed_by IS NOT NULL THEN
        SELECT role INTO reviewer_role FROM users WHERE id = NEW.reviewed_by;
        IF reviewer_role IS DISTINCT FROM 'clinician' THEN
            RAISE EXCEPTION 'review_flags.reviewed_by must reference a user with role clinician';
        END IF;

        IF NOT EXISTS (
            SELECT 1
            FROM patients
            WHERE user_id = NEW.patient_id
              AND clinician_id = NEW.reviewed_by
        ) THEN
            RAISE EXCEPTION 'review_flags.reviewed_by must be assigned to review_flags.patient_id';
        END IF;
    END IF;

    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER review_flags_require_matching_patient_and_clinician_reviewer
BEFORE INSERT OR UPDATE OF patient_id, message_id, reviewed_by ON review_flags
FOR EACH ROW EXECUTE FUNCTION enforce_review_flag_relationships();

CREATE FUNCTION prevent_referenced_user_role_change()
RETURNS TRIGGER AS $$
BEGIN
    IF NEW.role = OLD.role THEN
        RETURN NEW;
    END IF;

    IF EXISTS (SELECT 1 FROM patients WHERE user_id = OLD.id) THEN
        RAISE EXCEPTION 'cannot change role for a user with a patient profile';
    END IF;

    IF EXISTS (SELECT 1 FROM patients WHERE clinician_id = OLD.id) THEN
        RAISE EXCEPTION 'cannot change role for a clinician assigned to patients';
    END IF;

    IF EXISTS (SELECT 1 FROM review_flags WHERE reviewed_by = OLD.id) THEN
        RAISE EXCEPTION 'cannot change role for a clinician assigned to review flags';
    END IF;

    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER users_prevent_referenced_role_change
BEFORE UPDATE OF role ON users
FOR EACH ROW EXECUTE FUNCTION prevent_referenced_user_role_change();

CREATE FUNCTION prevent_review_flag_session_owner_change()
RETURNS TRIGGER AS $$
BEGIN
    IF NEW.patient_id <> OLD.patient_id
       AND EXISTS (
           SELECT 1
           FROM messages
           JOIN review_flags ON review_flags.message_id = messages.id
           WHERE messages.session_id = OLD.id
       ) THEN
        RAISE EXCEPTION 'cannot change session patient when a session message has a review flag';
    END IF;

    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER sessions_prevent_review_flag_owner_change
BEFORE UPDATE OF patient_id ON sessions
FOR EACH ROW EXECUTE FUNCTION prevent_review_flag_session_owner_change();

CREATE FUNCTION prevent_review_flag_message_session_change()
RETURNS TRIGGER AS $$
BEGIN
    IF NEW.session_id <> OLD.session_id
       AND EXISTS (
           SELECT 1
           FROM review_flags
           JOIN sessions ON sessions.id = NEW.session_id
           WHERE review_flags.message_id = OLD.id
             AND review_flags.patient_id <> sessions.patient_id
       ) THEN
        RAISE EXCEPTION 'cannot move a flagged message to a session for another patient';
    END IF;

    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER messages_prevent_review_flag_session_change
BEFORE UPDATE OF session_id ON messages
FOR EACH ROW EXECUTE FUNCTION prevent_review_flag_message_session_change();

CREATE INDEX sessions_patient_started_at_idx ON sessions (patient_id, started_at DESC);
CREATE INDEX messages_session_created_at_idx ON messages (session_id, created_at);
CREATE INDEX emotion_windows_session_ts_idx ON emotion_windows (session_id, ts);
CREATE INDEX review_flags_patient_reviewed_at_idx ON review_flags (patient_id, reviewed_at);
