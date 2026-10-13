using System;
using Microsoft.EntityFrameworkCore.Migrations;

#nullable disable

namespace AppointmentIntegration.Api.Migrations
{
    /// <inheritdoc />
    public partial class GCN51AppointmentPaymentConfirmationTime : Migration
    {
        /// <inheritdoc />
        protected override void Up(MigrationBuilder migrationBuilder)
        {
            migrationBuilder.AddColumn<DateTime>(
                name: "ConfirmedAtUtc",
                table: "AppointmentPayments",
                type: "datetime(6)",
                nullable: true);
        }

        /// <inheritdoc />
        protected override void Down(MigrationBuilder migrationBuilder)
        {
            migrationBuilder.DropColumn(
                name: "ConfirmedAtUtc",
                table: "AppointmentPayments");
        }
    }
}
