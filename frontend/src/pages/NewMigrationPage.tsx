import { useState } from "react";

import { navigate } from "../app/router";
import { AppFrame } from "../components/AppFrame";
import { api, ApiError } from "../services/api";
import { MigrationIntakeForm } from "../features/migration-intake/MigrationIntakeForm";
import type { MigrationCreate } from "../types";

export function NewMigrationPage() {
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [savedRequestId, setSavedRequestId] = useState<string | null>(null);

  const handleSubmit = async (payload: MigrationCreate) => {
    setIsSubmitting(true);
    setErrorMessage(null);
    setSavedRequestId(null);

    let createdRequestId: string | null = null;

    try {
      const migration = await api.createMigration(payload);
      createdRequestId = migration.request_id;
      setSavedRequestId(createdRequestId);

      await api.createRecommendation({
        ...payload,
        request_id: migration.request_id,
      });
      navigate(`/recommendation/${migration.request_id}`);
    } catch (error) {
      if (createdRequestId) {
        const suffix =
          error instanceof ApiError
            ? ` ${error.message}`
            : " Please review the saved assessment and retry.";
        setErrorMessage(
          `Assessment ${createdRequestId} was saved, but recommendation generation did not complete.${suffix}`,
        );
      } else if (error instanceof ApiError) {
        setErrorMessage(error.message);
      } else {
        setErrorMessage("An unexpected error occurred while requesting a recommendation.");
      }
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <AppFrame
      eyebrow="Migration Assessment"
      title="Create a migration assessment"
      summary="Capture the migration scope and technical constraints needed to recommend the best Oracle-to-Oracle migration approach."
    >
      <MigrationIntakeForm
        onSubmit={handleSubmit}
        isSubmitting={isSubmitting}
        errorMessage={errorMessage}
        errorAction={
          savedRequestId ? (
            <button
              className="secondary-button"
              type="button"
              onClick={() => navigate(`/migration/${savedRequestId}`)}
            >
              Open saved assessment
            </button>
          ) : undefined
        }
      />
    </AppFrame>
  );
}
