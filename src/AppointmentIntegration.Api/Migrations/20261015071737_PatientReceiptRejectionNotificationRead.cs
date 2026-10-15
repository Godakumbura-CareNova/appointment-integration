using System;
using Microsoft.EntityFrameworkCore.Migrations;

#nullable disable

namespace AppointmentIntegration.Api.Migrations
{
    /// <inheritdoc />
    public partial class PatientReceiptRejectionNotificationRead : Migration
    {
        /// <inheritdoc />
        protected override void Up(MigrationBuilder migrationBuilder)
        {
            migrationBuilder.AddColumn<DateTime>(
                name: "PatientNotificationReadAtUtc",
                table: "AppointmentReceipts",
                type: "datetime(6)",
                nullable: true);
        }

        /// <inheritdoc />
        protected override void Down(MigrationBuilder migrationBuilder)
        {
            migrationBuilder.DropColumn(
                name: "PatientNotificationReadAtUtc",
                table: "AppointmentReceipts");
        }
    }
}
