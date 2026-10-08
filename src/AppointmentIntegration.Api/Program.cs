var builder = WebApplication.CreateBuilder(args);
builder.Configuration.AddJsonFile("publiccontent.json", optional: false, reloadOnChange: true);
// Environment and command-line settings override the public-content defaults.
builder.Configuration.AddEnvironmentVariables();
builder.Configuration.AddCommandLine(args);

// Add services to the container.

builder.Services.AddControllers();
builder.Services.Configure<AppointmentIntegration.Api.Services.PublicContentOptions>(builder.Configuration.GetSection("PublicContent"));
builder.Services.AddHttpClient("PublicContent", client => client.Timeout = TimeSpan.FromSeconds(5));
builder.Services.AddScoped<AppointmentIntegration.Api.Services.PublicContentService>();
builder.Services.AddCors(options => options.AddPolicy("PublicFrontend", policy => policy
    .WithOrigins(builder.Configuration.GetSection("PublicContent:AllowedOrigins").Get<string[]>() ?? ["http://localhost:3000"])
    .AllowAnyHeader().AllowAnyMethod()));
// Learn more about configuring Swagger/OpenAPI at https://aka.ms/aspnetcore/swashbuckle
builder.Services.AddEndpointsApiExplorer();
builder.Services.AddSwaggerGen();

var app = builder.Build();

// Configure the HTTP request pipeline.
if (app.Environment.IsDevelopment())
{
    app.UseSwagger();
    app.UseSwaggerUI();
}

app.UseHttpsRedirection();

app.UseCors("PublicFrontend");
app.UseAuthorization();

app.MapControllers();

app.Run();
public partial class Program { }
