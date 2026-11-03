import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Separator } from "@/components/ui/separator";
import { SurveyTools } from "./gen/surmap/agent/v1/survey_tools_pb";

export default function App() {
  return (
    <main className="mx-auto flex min-h-svh max-w-2xl items-center p-4">
      <Card className="w-full">
        <CardHeader>
          <CardTitle>
            <h2>SurveyTools</h2>
          </CardTitle>
          <p className="text-sm text-muted-foreground">
            Placeholder until the chat UI lands. The rpcs below come from the generated descriptor.
          </p>
        </CardHeader>
        <Separator />
        <CardContent className="pt-6">
          <ul aria-label="SurveyTools rpcs" className="flex flex-col gap-2 font-mono text-sm">
            {SurveyTools.methods.map((method) => (
              <li key={method.name}>{method.name}</li>
            ))}
          </ul>
        </CardContent>
      </Card>
    </main>
  );
}
