import React from 'react';
import Icon from './Icon';

export const STARTER_TARGET = 40;

/** Suggestions shown above the wardrobe: complete the profile, then complete a small wardrobe */
export default function WardrobeNudges({ user, wardrobe, openStarter, openProfile }) {
  const missingProfile = user && !user.gender;
  const small = wardrobe.length > 0 && wardrobe.length < STARTER_TARGET;
  if (!missingProfile && !small) return null;

  return (
    <div className="nudges">
      {missingProfile && (
        <div className="nudge">
          <Icon name="user" />
          <p><strong>Complétez votre profil</strong> — sexe, tailles, styles et couleurs préférés : la garde-robe de départ,
            le catalogue et les tailles des pièces s’y adaptent.</p>
          <button className="btn btn-ghost btn-sm" onClick={openProfile}>Compléter</button>
        </div>
      )}
      {small && (
        <div className="nudge">
          <Icon name="sparkle" />
          <p><strong>Votre garde-robe ne compte que {wardrobe.length} pièce{wardrobe.length > 1 ? 's' : ''}.</strong> Ajoutez une
            garde-robe de départ de {STARTER_TARGET}+ vraies pièces adaptées (hauts, bas, chaussures, accessoires) — vos pièces
            actuelles sont conservées.</p>
          <button className="btn btn-primary btn-sm" onClick={openStarter}>Compléter ma garde-robe</button>
        </div>
      )}
    </div>
  );
}
