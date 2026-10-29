import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import OutfitRepeatOption from "./OutfitRepeatOption";

describe("outfit repeat option", () => {
  it("is available even when another requirement remains unresolved", () => {
    const html = renderToStaticMarkup(<OutfitRepeatOption allowed={false} confirmed={false}
      legacyService={false} otherRequirements={true} loading={false} onAllow={() => {}} />);
    expect(html).toContain("Allow outfit repeats &amp; retry");
    expect(html).not.toContain("disabled=\"\"");
    expect(html).toContain("Rain protection, other weather needs and your luggage limit still apply.");
    expect(html).toContain("You will still need to address the items listed above.");
  });

  it("explains that the older service must be restarted", () => {
    const html = renderToStaticMarkup(<OutfitRepeatOption allowed={false} confirmed={false}
      legacyService={true} otherRequirements={false} loading={false} onAllow={() => {}} />);
    expect(html).toContain("disabled=\"\"");
    expect(html).toContain("Restart it to enable outfit repeats");
  });

  it("shows when repeats are already allowed", () => {
    const html = renderToStaticMarkup(<OutfitRepeatOption allowed={true} confirmed={false}
      legacyService={false} otherRequirements={false} loading={false} onAllow={() => {}} />);
    expect(html).toContain("Outfit repeats allowed");
    expect(html).toContain("disabled=\"\"");
  });
});
