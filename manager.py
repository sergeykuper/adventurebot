from agents import Runner, trace, gen_trace_id, Agent
from agents.result import RunResult
from agents.mcp import MCPServerStdio
from .models import TripQuery, TripContext
from .agents import (
    create_weather_agent,  WeatherAnalysis,
    create_activity_search_agent, SearchResult,
    create_recommendation_agent, TripPlan,
)

class AdventureManager:
    """Manages the simplified adventure planning workflow with handoff and custom tool examples."""

    def __init__(self):
        self.activity_search_agent: Agent[TripContext] = create_activity_search_agent()
        self.recommendation_agent: Agent[TripContext] = create_recommendation_agent()

    async def run(self, query: TripQuery) -> None:
        """Run the simplified adventure planning workflow"""
        trace_id = getn_trace_id()
        print(f"Starting adventure planning... (Trace ID: {trace_id})")
        print(f"View trace: https://platform.openai.com/traces/trace?trace_id={trace_id}")

        # Create the context object
        trip_context = TripContext(query=query)

        with trace("Adventure Planning (Simplified)", trace_id=trace_id):
            # 1. Get Weather Information
            weather_info = await self._get_weather_info(trip_context)

            # 2. Search for Activities (potentially involves handoff)
            search_results, search_agent_used = await self._search_for_activities(trip_context, weather_info)

            # 3. Generate Trip Plan (includes evaluation and recommendations)
            trip_plan = await self._generate_trip_plan(search_results, weather_info, trip_context)

            # Display the final trip plan
            self._print_trip_plan(trip_plan)

    async def _get_weather_info(self, context: TripContext) -> WeatherAnalysis:
        """Run the WeatherAgent to get weather information, managing MCP server lifecycle."""
        print("Initializing and connecting to Weather MCP server...")

        # Define and connect to the MCP server explicitly
        weather_mcp_server = MCPServerStdio(
            params={
                "command": "docker",
                "args": ["run", "--rm", "-i", "mcp_server_weather"]
            }
        )

        async with weather_mcp_server as server:
            print("Weather MCP server connected. Creating Weather Agent...")
            weather_agent = create_weather_agent(mcp_servers=[server])

            print("Fetching weather information using Weather Agent...")
            input_str = (
                f"Get weather analysis for a trip to {context.query.location}"
                f"from {context.query.start_date} to {context.query.end_date}."
            )

            result = await Runner.run(
                weather_agent,
                input_str,
                context=context
            )

            weather_info = result.final_output_as(WeatherAnalysis)
            print("Weather information fetched.")

        print("Weather MCP server disconnected.")
        return weather_info
    
    async def _search_for_activities(self, context: TripContext, weather_info: WeatherAnalysis) -> tuple[SearchResult, Agent]:
        """Run the ActivitySearchAgent, handling potential handoff to KidFriendlyActivityAgent."""
        print("Searching for activities (checking for kid-friendly handoff)...")

        # Prepare input string including trip details and weather context
        participants_str = f"{context.query.participant_number} participants (ages: {context.query.participant_ages})"
        input_str = (
            f"Find activities for a trip to {context.query.location} "
            f"from {context.query.start_date} to {context.query.end_date} "
            f"for {participants_str}.\n\n"
            f"Consider the following weather summary:\n{weather_info.summary}"
        )

        # Run the initial search agent
        result: RunResult[SearchResult] = await Runner.run(
            self.activity_search_agent,
            input_str,
            context=context
        )

        search_results = result.final_output_as(SearchResult)
        final_agent = result.last_agent

        # Log in a handoff occured
        if final_agent.name != self.activity_search_agent.name:
            print(f"Handoff occured: Activities found by {final_agent.name}.")
        else:
            print(f"Activity search complete (using {final_agent.name}).")

        return search_results, final_agent
    

    async def _generate_trip_plan(
            self,
            search_results: SearchResult,
            weather_info: WeatherAnalysis,
            context: TripContext
    ) -> TripPlan:       
        """Run the RecommendationAgent to evaluate activities and create the final plan."""
        print("Evaluating activities and creating trip plan...")

        # Create input string with all context
        agent_used = "regular search agent"
        if search_results.kid_friendly_focused:
            agent_used = "kid-friendly agent"

        # Prepare input string including all necessary context
        participants_str = f"{context.query.participant_number} participants (ages: {context.query.participant_ages})"
        dates_str = f"{context.query.start_date} to {context.query.end_date}"
        input_str = (
            f"Create a trip plan for {context.query.location} from {dates_str}"
            f"for {participants_str}.\n\n"
            f"Weather Information:\n{weather_info.model_dump()}\n\n"
            f"Potential Activities Found:\n{search_results.model_dump()}"
        )

        result = await Runner.run(
            self.recommendation_agent,
            input_str,
            context=context
        )

        trip_plan = result.final_output_as(TripPlan)
        print("Trip plan generated.")
        return trip_plan
    
    def _print_trip_plan(self, plan: TripPlan) -> None:
        """Print the final trip plan in a structured format."""
        print("\n=== Your Adventure Plan ===\n")
        print(f"Location: {plan.location}")
        print(f"Dates: {plan.dates}")
        print(f"Participants: {plan.participants_summary}\n")
        
        print(f"Weather Summary:\n{plan.weather_summary}\n")

        print("Recommended Activities:")

        if not plan.recommended_activities:
            print("- No specific activities recommended based on search and evaluation.")
        for activity in plan.recommended_activities:
            print(f"\n- {activity.name}")
            print(f"  Description: {activity.description}")
            print(f" Reasoning {activity.reasoning}")
            if activity.best_time:
                print(f" Best Time: {activity.best_time}")
            if activity.source_url:
                print(f"  More Info: {activity.source_url}")
            if activity.weather_considerations:
                print("  Weather Considerations:")
                for consideration in activity.weather_considerations:
                    print(f"   -consideration")
            if activity.preparation_tips:
                print("  Preparation Tips:")
                for tip in activity.preparation_tips:
                    print("   - {tip}")
        
        print("\nPacking List:")
        if not plan.packing_list:
            print("- No specific packing items suggested.")
        for item in plan.packing_list:
            print(f"- {item}")
        
        print("\nGeneral Tips:")
        if not plan.general_tips:
            print("- No general tips provided.")
        for tip in plan.general_tips:
            print(f"- {tip}")








